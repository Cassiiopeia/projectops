"""oss_cli — 판정 없이 사실만 내는지, 부분 실패·절단·안전 가드가 동작하는지 확인한다 (#644, #660).

네트워크는 `oss_cli._call` 을 대체해 모킹한다. 실제 git 이 필요한 local-facts 는 tmp_path 에 샘플 레포를 만든다.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import email.message
import importlib.util
import io
import json
import os
import re
import socket
import subprocess
import urllib.error
from pathlib import Path

import pytest

_CLI = Path(__file__).resolve().parents[1] / "scripts" / "oss_cli.py"
_spec = importlib.util.spec_from_file_location("oss_cli", _CLI)
oss_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oss_cli)
gh = oss_cli.gh_client

PAT = "SECRETPAT123"


# ── 공통 도구 ────────────────────────────────────────────────────────────

def run(argv, capsys):
    rc = oss_cli.run_cli(oss_cli.build_parser(), argv)
    return rc, json.loads(capsys.readouterr().out)


def api_err(status, message="x", headers=None):
    e = gh.GitHubAPIError(status, message)
    e.headers = {k.lower(): v for k, v in (headers or {}).items()}
    return e


def b64(text):
    return {"content": base64.b64encode(text.encode()).decode()}


def listing(**names):
    return [{"name": n, "type": t} for n, t in names.items()]


class FakeAPI:
    """경로 → 응답(값·예외·호출가능). 정확히 같은 경로가 먼저, 그다음 prefix(긴 것 우선)."""

    def __init__(self, exact=None, prefix=None):
        self.exact = dict(exact or {})
        self.prefix = sorted((prefix or {}).items(), key=lambda kv: -len(kv[0]))
        self.calls = []

    def __call__(self, method, path, pat, data=None):
        self.calls.append((method, path, data))
        assert pat == PAT
        hit = self.exact.get((method, path))
        if hit is None:
            for pre, val in self.prefix:
                if path.startswith(pre):
                    hit = val
                    break
        if hit is None:
            raise api_err(404, "Not Found")
        if callable(hit):
            hit = hit(path, data)
        if isinstance(hit, Exception):
            raise hit
        return hit


def repo_meta(**over):
    m = {"description": "d", "homepage": "", "topics": ["a"], "language": "Python",
         "license": {"spdx_id": "MIT"}, "stargazers_count": 3, "forks_count": 1, "open_issues_count": 2,
         "created_at": "2026-01-01T00:00:00Z", "pushed_at": "2026-09-01T00:00:00Z",
         "archived": False, "fork": False, "is_template": False, "private": False, "has_discussions": False,
         "has_pages": False, "has_wiki": True, "default_branch": "main"}
    m.update(over)
    return m


def collect_api(**over):
    """collect 가 부르는 엔드포인트를 전부 채운 기본 가짜 API."""
    p = "/repos/o/r"
    prefix = {
        f"{p}/contents/.github/ISSUE_TEMPLATE": listing(**{"bug.yml": "file", "config.yml": "file"}),
        f"{p}/contents/.github/workflows": listing(**{"ci.yml": "file"}),
        f"{p}/contents/.github": listing(**{"CODE-OF-CONDUCT.md": "file"}),
        f"{p}/contents/docs": listing(),
        f"{p}/contents/CONTRIBUTING.md": b64("# Contributing\nline2\n"),
        f"{p}/contents/": listing(**{"README.md": "file", "LICENSE": "file", "CONTRIBUTING.md": "file"}),
        f"{p}/labels": [{"name": "bug", "color": "d73a4a", "description": ""}],
        f"{p}/readme": b64("# T\n\nhello\n"),
        f"{p}/releases": [],
        f"{p}/tags": [{"name": "v1"}, {"name": "v2"}],
        f"{p}/issues": [
            {"number": 5, "title": "q", "state": "open", "labels": [{"name": "bug"}], "user": {"login": "u"},
             "author_association": "NONE", "comments": 1, "created_at": "c", "updated_at": "u"},
            {"number": 6, "title": "pr", "state": "open", "labels": [], "user": {"login": "v"},
             "author_association": "MEMBER", "comments": 0, "created_at": "c2", "updated_at": "u2",
             "pull_request": {}},
        ],
    }
    exact = {("GET", p): repo_meta()}
    exact.update(over.pop("exact", {}))
    prefix.update(over)
    return FakeAPI(exact, prefix)


@pytest.fixture(autouse=True)
def fake_pat(monkeypatch):
    monkeypatch.setattr(oss_cli, "_pat", lambda o, r: PAT)


# ── 순수 함수: README·파일 탐지 ──────────────────────────────────────────

def test_readme_gives_raw_top_and_headings_not_verdicts():
    text = "# Tool\n\n![demo](docs/demo.gif)\n\n## Why\n\n```bash\nnpx tool\n```\n\n## vs Others\n"
    r = oss_cli.analyze_readme(text)
    assert r["present"] is True
    assert r["top"].startswith("# Tool")
    assert "## vs Others" in r["headings"]
    assert r["first_code_block_line"] == 7
    assert r["media"][0]["ref"].endswith("demo.gif")
    # 판정 키를 만들지 않는다 — 에이전트가 원문을 읽고 판단한다
    for verdict in ("has_benchmark_section", "has_comparison_section", "demo_media"):
        assert verdict not in r


def test_readme_measures_non_english_and_skips_badges_as_media():
    text = "# 도구\n\n[![ci](https://img.shields.io/badge/ci-ok-green.svg)](x)\n\n한국어 설명입니다\n\nSee README.ko.md\n"
    r = oss_cli.analyze_readme(text)
    assert r["badges"] == 1
    assert r["media"] == []
    assert 0.3 < r["non_english_ratio"] < 0.5  # 한글 8자 : 영문 12자 (URL·링크 주소 제외)
    assert r["translations_linked"] == ["ko"]


def test_missing_readme():
    assert oss_cli.analyze_readme(None) == {"present": False}


def test_readme_top_lines_follow_argument_and_truncation_is_reported():
    text = "\n".join(f"line {i}" for i in range(100)) + "\n" + "\n".join(f"## h{i}" for i in range(70))
    r = oss_cli.analyze_readme(text, top_lines=5)
    assert r["top"].splitlines() == [f"line {i}" for i in range(5)]
    assert r["headings_total"] == 70 and r["headings_truncated"] is True and len(r["headings"]) == 60
    assert oss_cli.analyze_readme(text)["top"].count("\n") == oss_cli.TOP_LINES - 1


def test_text_head_gives_first_lines_and_total():
    r = oss_cli.text_head("\n".join(str(i) for i in range(40)), 15)
    assert r["lines"] == 40 and r["head"].splitlines()[-1] == "14"
    assert oss_cli.text_head(None) == {"head": "", "lines": 0}


def test_detect_files_checks_three_places_and_flags_license_folder():
    root = {"LICENSE": "dir", "README.md": "file", "docs": "dir"}
    gh_ = {"CONTRIBUTING.md": "file", "ISSUE_TEMPLATE": "dir"}
    docs = {"SECURITY.md": "file"}
    f = oss_cli.detect_files(root, gh_, docs, ["bug.yml", "feature.yml", "config.yml"])
    assert f["contributing"]["where"] == ".github"
    assert f["security"]["where"] == "docs"
    assert f["license"]["license_is_dir"] is True  # 폴더 LICENSE는 GitHub이 인식하지 못한다 — 사실 필드로만
    assert "warning" not in f["license"]
    assert f["issue_templates"] == {"forms_yml": 2, "markdown": 0, "config_yml": True}
    assert f["code_of_conduct"] is None
    assert f["docs_dir"] is True


@pytest.mark.parametrize("key,name,where", [
    ("code_of_conduct", "CODE-OF-CONDUCT.md", ".github"),   # cli/cli 실측
    ("code_of_conduct", "code_of_conduct.rst", "root"),
    ("changelog", "CHANGES.rst", "root"),                     # pallets/flask 실측
    ("changelog", "Release-Notes.md", "root"),
    ("license", "license.md", "root"),
    ("license", "COPYING.txt", "root"),
    ("contributing", "Contributing.MD", "root"),
    ("security", "SECURITY.adoc", "root"),
    ("funding", "FUNDING.yml", "root"),
    ("citation", "CITATION.cff", "root"),
    ("pr_template", "pull_request_template.md", "root"),
    ("dependabot", "renovate.json5", "root"),
])
def test_health_names_tolerate_case_hyphen_and_extension(key, name, where):
    listing_ = {name: "file"}
    root, gh_ = ({name: "file"}, {}) if where == "root" else ({}, {name: "file"})
    f = oss_cli.detect_files(root, gh_, {}, [])
    assert f[key] and f[key]["name"] == name and f[key]["where"] == where


def test_health_names_do_not_overmatch():
    f = oss_cli.detect_files({"LICENSES": "dir", "securityfix.py": "file", "CONTRIBUTING_old.md": "file"}, {}, {}, [])
    assert f["license"] is None and f["security"] is None and f["contributing"] is None


def test_file_beats_directory_with_same_stem():
    f = oss_cli.detect_files({"LICENSE": "dir", "LICENSE.md": "file"}, {}, {}, [])
    assert f["license"]["name"] == "LICENSE.md" and "license_is_dir" not in f["license"]


def test_claude_md_is_distinguishable_from_agents_md():
    f = oss_cli.detect_files({"CLAUDE.md": "file"}, {}, {}, [])
    assert f["agents_md"]["name"] == "CLAUDE.md" and f["claude_md"]["name"] == "CLAUDE.md"
    f2 = oss_cli.detect_files({"AGENTS.md": "file"}, {}, {}, [])
    assert f2["agents_md"]["name"] == "AGENTS.md" and f2["claude_md"] is None


def test_detect_files_reports_app_facts_without_verdict():
    root = {"README.md": "file", "android": "dir", "ios": "dir", "PRIVACY_POLICY.md": "file"}
    f = oss_cli.detect_files(root, {}, {}, [])
    assert f["privacy_policy"]["name"] == "PRIVACY_POLICY.md"
    assert f["mobile_dirs"] == ["android", "ios"]
    assert f["store_metadata_root"] is False  # 루트에 없다는 사실만. 하위 fastlane 은 에이전트가 확인한다
    assert oss_cli.detect_files({"README.md": "file"}, {}, {}, [])["privacy_policy"] is None


def test_privacy_policy_found_one_level_below_and_searched_is_reported():
    root = {"docs": "dir"}
    docs = {"store": "dir"}
    extra = {"docs/store": {"privacy-policy.md": "file"}}
    f = oss_cli.detect_files(root, {}, docs, [], extra)
    assert f["privacy_policy"] == {"where": "docs/store", "name": "privacy-policy.md", "type": "file"}
    assert "docs/store" in f["privacy_searched"] and "root" in f["privacy_searched"]
    assert oss_cli.extra_privacy_dirs({"fastlane": "dir", "store": "dir"}, {"legal": "dir", "x": "dir"}) == \
        ["docs/legal", "store", "fastlane/metadata"]


def test_labels_are_passed_through_without_classification():
    out = oss_cli.summarize_labels(["type: bug", "good first issue", "작업중"])
    assert out == {"count": 3, "names": ["type: bug", "good first issue", "작업중"], "truncated": False, "capped": False}
    big = oss_cli.summarize_labels([f"l{i}" for i in range(200)], capped=True)
    assert big["truncated"] is True and big["capped"] is True and len(big["names"]) == 150 and big["count"] == 200


# ── 순수 함수: 로컬 측정 ─────────────────────────────────────────────────

def test_co_change_counts_pairs_and_skips_bulk_commits():
    commits = [["a.py", "b.py"], ["a.py", "b.py", "c.py"], ["a.py", "b.py"], [f"f{i}.py" for i in range(40)]]
    r = oss_cli.co_change(commits)
    assert r["unit"] == "commit"  # PR 단위가 아니라는 한계를 값으로 남긴다
    assert r["top_pairs"][0] == {"a": "a.py", "b": "b.py", "count": 3}
    assert r["max_files_per_commit"] == 40
    assert all(p["a"].startswith("f") is False for p in r["top_pairs"])  # 대량 변경은 쌍에서 제외
    assert r["excluded"]["large_commits"] == 1


def test_co_change_drops_version_sync_and_lock_files_and_says_so():
    commits = [["plugin.json", "marketplace.json", "src/a.py"], ["plugin.json", "marketplace.json", "src/a.py"],
               ["yarn.lock", "src/a.py", "src/b.py"], ["yarn.lock", "src/a.py", "src/b.py"]]
    r = oss_cli.co_change(commits)
    assert [(p["a"], p["b"]) for p in r["top_pairs"]] == [("src/a.py", "src/b.py")]
    assert r["excluded"]["noise_file_entries"] == 6


def test_natural_language_strings_skip_catalogs_and_non_source():
    files = {
        "src/a.py": 'msg = "안녕하세요"\nx = "ok"\n',
        "locales/ko.py": 'M = "카탈로그 안"\n',
        "README.md": '"한글"',
    }
    r = oss_cli.natural_language_strings(files)
    assert r["total"] == 1 and r["top_files"][0]["path"] == "src/a.py"


def test_natural_language_strings_skip_tests_and_comment_lines():
    files = {
        "src/a.py": '# "주석 안 한글"\nmsg = "화면 문구"\n',
        "tests/test_a.py": 'x = "테스트 문구"\n',
        "src/b_test.go": 's := "테스트"\n',
        "web/app.spec.ts": 'const s = "스펙"\n',
        "src/c.ts": '// "주석"\n/* "블록" */\n * "별표"\nconst t = "진짜 문구"\n',
    }
    r = oss_cli.natural_language_strings(files)
    assert r["total"] == 2 and {f["path"] for f in r["top_files"]} == {"src/a.py", "src/c.ts"}
    assert r["excluded_test_files"] == 3


def test_committed_secret_paths_ignore_examples():
    tracked = [".env", ".env.example", "config/key.pem", "src/app.py", "android/key.jks", "a/.env.sample"]
    assert oss_cli.committed_secret_paths(tracked) == [".env", "config/key.pem", "android/key.jks"]


def test_dependency_names_from_manifests():
    r = oss_cli.dependency_names({
        "package.json": '{"dependencies":{"react":"1"},"devDependencies":{"jest":"1"}}',
        "requirements.txt": "requests>=2\n# c\n-r other.txt\nflask==1\n",
        "pubspec.yaml": "name: x\ndependencies:\n  flutter:\n    sdk: flutter\n  http: ^1.0.0\ndev_dependencies:\n  lints: ^2.0.0\n",
    })
    assert r["package.json"] == ["react", "jest (devDependencies)"]
    assert r["requirements.txt"] == ["requests", "flask"]
    assert r["pubspec.yaml"] == ["http", "lints (dev)"]


def test_dependency_names_jvm_python_rust_ruby_php():
    r = oss_cli.dependency_names({
        "build.gradle": "dependencies {\n  implementation 'com.squareup.okhttp3:okhttp:4.12.0'\n"
                        "  testImplementation(\"junit:junit:4.13\")\n}\n",
        "pom.xml": "<dependencies><dependency><groupId>org.x</groupId><artifactId>lib</artifactId></dependency></dependencies>",
        "pyproject.toml": '[project]\ndependencies = [\n  "requests>=2",\n  "rich",\n]\n',
        "Cargo.toml": '[dependencies]\nserde = "1"\n[dev-dependencies]\ncriterion = "0.5"\n',
        "Gemfile": "source 'x'\ngem 'rails'\n  gem \"rake\"\n",
        "composer.json": '{"require":{"php":">=8","ext-json":"*","monolog/monolog":"^3"}}',
    })
    assert r["build.gradle"] == ["com.squareup.okhttp3:okhttp", "junit:junit (test)"]
    assert r["pom.xml"] == ["org.x:lib"]
    assert r["pyproject.toml"] == ["requests", "rich"]
    assert r["Cargo.toml"] == ["serde", "criterion (dev)"]
    assert r["Gemfile"] == ["rails", "rake"]
    assert r["composer.json"] == ["monolog/monolog"]


def test_manifest_classification_separates_supported_and_unsupported():
    assert oss_cli.is_manifest("app/build.gradle.kts") and oss_cli.is_manifest("requirements-dev.txt")
    assert not oss_cli.is_manifest("Package.swift")
    assert oss_cli.is_unsupported_manifest("ios/Podfile") and oss_cli.is_unsupported_manifest("a/B.csproj")
    assert not oss_cli.is_unsupported_manifest("package.json")


# ── 오류 분류 ────────────────────────────────────────────────────────────

def test_classify_rate_limit_vs_permission():
    rl = oss_cli.classify_api_error(api_err(403, "API rate limit exceeded", {"X-RateLimit-Remaining": "0",
                                                                             "X-RateLimit-Reset": "1893456000"}))
    assert rl["code"] == "rate_limited" and "다시 실행" in rl["next"]
    assert oss_cli.classify_api_error(api_err(429, "slow down", {"Retry-After": "30"}))["code"] == "rate_limited"
    assert oss_cli.classify_api_error(api_err(403, "Resource not accessible"))["code"] == "http_403"
    n404 = oss_cli.classify_api_error(api_err(404))["next"]
    assert "오타" in n404 and "비공개" in n404  # 둘 다 안내한다
    assert oss_cli.classify_api_error(api_err(401))["code"] == "http_401"
    assert oss_cli.classify_api_error(gh.GitHubNetworkError("URLError: x"))["code"] == "network"


def test_request_json_passes_timeout_and_splits_network_errors(monkeypatch):
    seen = {}

    def boom(req, timeout=None):
        seen["timeout"] = timeout
        raise socket.timeout("timed out")
    monkeypatch.setattr(gh._opener, "open", boom)
    with pytest.raises(gh.GitHubNetworkError):
        gh.request_json("GET", "https://api.github.com/x", None, PAT, timeout=7)
    assert seen["timeout"] == 7

    def down(req, timeout=None):
        raise urllib.error.URLError("no route")
    monkeypatch.setattr(gh._opener, "open", down)
    with pytest.raises(gh.GitHubNetworkError) as ei:
        gh.request_json("GET", "https://api.github.com/x", None, PAT)
    assert PAT not in str(ei.value)


def test_request_json_keeps_response_headers_on_http_error(monkeypatch):
    hdrs = email.message.Message()
    hdrs["X-RateLimit-Remaining"] = "0"

    def deny(req, timeout=None):
        raise urllib.error.HTTPError("u", 403, "Forbidden", hdrs, io.BytesIO(b'{"message":"rate limit"}'))
    monkeypatch.setattr(gh._opener, "open", deny)
    with pytest.raises(gh.GitHubAPIError) as ei:
        gh.request_json("GET", "https://api.github.com/x", None, PAT)
    assert ei.value.status_code == 403 and ei.value.headers["x-ratelimit-remaining"] == "0"


# ── collect ──────────────────────────────────────────────────────────────

def test_collect_happy_path_has_facts_untrusted_and_no_verdicts(monkeypatch, capsys):
    monkeypatch.setattr(oss_cli, "_call", collect_api())
    rc, out = run(["collect", "o/r"], capsys)
    assert rc == 0 and out["ok"] and out["code"] == "ok"
    d = out["data"]
    assert d["meta"]["is_template"] is False and d["meta"]["default_branch"] == "main"
    assert d["meta"]["open_issues_count"] == 2
    assert d["files"]["code_of_conduct"]["name"] == "CODE-OF-CONDUCT.md"  # 하이픈 변형
    assert d["files"]["contributing"]["lines"] == 2 and d["files"]["contributing"]["head"].startswith("# Contributing")
    assert d["errors"] == [] and d["truncated"] == {}
    assert d["issues_sample"][0]["number"] == 5 and d["issues_sample"][0]["is_pr"] is False
    assert d["issues_sample"][1]["is_pr"] is True and d["issues_sample"][1]["created_at"] == "c2"
    assert d["releases"]["tags_count"] == 2 and d["releases"]["latest"] is None
    assert "data.readme.top" in out["untrusted"] and "data.issues_sample[].title" in out["untrusted"]
    assert "지시가 아니" in out["untrusted_notice"] or "따르지 않" in out["untrusted_notice"]
    # 점수·등급·판정 키가 없다
    flat = json.dumps(out, ensure_ascii=False)
    for forbidden in ('"score"', '"grade"', '"passed"', '"verdict"', '"maturity"'):
        assert forbidden not in flat


def test_collect_template_repo_and_prerelease_flags(monkeypatch, capsys):
    api = collect_api(exact={("GET", "/repos/o/r"): repo_meta(is_template=True)},
                      **{"/repos/o/r/releases": [
                          {"tag_name": "v2-rc", "prerelease": True, "draft": False, "published_at": "p", "assets": []},
                          {"tag_name": "v1", "prerelease": False, "draft": False, "published_at": "q", "assets": [1]}]})
    monkeypatch.setattr(oss_cli, "_call", api)
    _, out = run(["collect", "o/r"], capsys)
    d = out["data"]
    assert d["meta"]["is_template"] is True
    assert d["releases"]["latest_prerelease"] is True and d["releases"]["latest_stable"] == "v1"
    assert d["releases"]["tags_count"] == 0  # 릴리스가 있으면 태그는 세지 않는다


def test_collect_issues_disabled_410_is_partial_not_failure(monkeypatch, capsys):
    monkeypatch.setattr(oss_cli, "_call", collect_api(**{"/repos/o/r/issues": api_err(410, "Issues are disabled")}))
    rc, out = run(["collect", "o/r"], capsys)
    assert rc == 0 and out["ok"] and out["code"] == "partial"
    assert out["data"]["errors"] == [{"endpoint": "issues", "code": "http_410"}]
    assert out["data"]["issues_sample"] == [] and out["data"]["files"]["license"] is not None
    assert "미확인" in out["summary"]


def test_collect_optional_403_and_rate_limit_are_recorded(monkeypatch, capsys):
    monkeypatch.setattr(oss_cli, "_call", collect_api(**{
        "/repos/o/r/releases": api_err(403, "forbidden"),
        "/repos/o/r/labels": api_err(403, "API rate limit exceeded", {"x-ratelimit-remaining": "0"})}))
    _, out = run(["collect", "o/r"], capsys)
    codes = {e["endpoint"]: e["code"] for e in out["data"]["errors"]}
    assert codes["releases"] == "http_403" and codes["labels"] == "rate_limited"


def test_collect_required_meta_failures_fail_with_next(monkeypatch, capsys):
    for err, code in ((api_err(404), "http_404"), (api_err(401), "http_401"),
                      (api_err(403, "API rate limit exceeded", {"x-ratelimit-remaining": "0"}), "rate_limited"),
                      (gh.GitHubNetworkError("TimeoutError: x"), "network")):
        monkeypatch.setattr(oss_cli, "_call", FakeAPI({("GET", "/repos/o/r"): err}))
        rc, out = run(["collect", "o/r"], capsys)
        assert rc == 1 and out["ok"] is False and out["code"] == code and out["next"]


def test_collect_no_pat(monkeypatch, capsys):
    monkeypatch.setattr(oss_cli, "_pat", lambda o, r: None)
    rc, out = run(["collect", "o/r"], capsys)
    assert rc == 1 and out["code"] == "no_pat" and out["next"]


def test_collect_empty_repo_and_missing_readme(monkeypatch, capsys):
    api = FakeAPI({("GET", "/repos/o/r"): repo_meta(), ("GET", "/repos/o/r/labels?per_page=100&page=1"): [],
                   ("GET", "/repos/o/r/releases?per_page=10"): [], ("GET", "/repos/o/r/tags?per_page=30"): [],
                   ("GET", "/repos/o/r/issues?state=all&per_page=30"): []})
    monkeypatch.setattr(oss_cli, "_call", api)  # 나머지(contents·readme)는 전부 404
    rc, out = run(["collect", "o/r"], capsys)
    d = out["data"]
    assert rc == 0 and d["readme"] == {"present": False} and d["root_entries"] == []
    assert d["files"]["license"] is None and d["errors"] == []


def test_collect_network_error_on_optional_keeps_going(monkeypatch, capsys):
    monkeypatch.setattr(oss_cli, "_call", collect_api(**{"/repos/o/r/tags": gh.GitHubNetworkError("URLError: x"),
                                                        "/repos/o/r/releases": []}))
    _, out = run(["collect", "o/r"], capsys)
    assert {"endpoint": "tags", "code": "network"} in out["data"]["errors"]


def test_collect_reports_truncation(monkeypatch, capsys):
    many = listing(**{f"f{i:03d}": "file" for i in range(100)})
    labels = [{"name": f"l{i}", "color": "x", "description": ""} for i in range(100)]
    api = collect_api(**{"/repos/o/r/contents/": many, "/repos/o/r/labels": labels,
                        "/repos/o/r/readme": b64("\n".join(f"## h{i}" for i in range(80)))})
    monkeypatch.setattr(oss_cli, "_call", api)
    _, out = run(["collect", "o/r"], capsys)
    t = out["data"]["truncated"]
    assert t["root_entries"] == {"total": 100, "shown": 80} and len(out["data"]["root_entries"]) == 80
    assert t["readme.headings"]["total"] == 80
    assert "labels.capped" in t and out["data"]["labels"]["capped"] is True  # 5페이지 모두 가득 → 상한
    assert "절단" in out["summary"]


def test_collect_label_truncation_over_150(monkeypatch, capsys):
    pages = {f"/repos/o/r/labels?per_page=100&page={i}": [{"name": f"p{i}l{j}"} for j in range(100 if i < 3 else 30)]
             for i in (1, 2, 3)}
    api = collect_api(exact={("GET", k): v for k, v in pages.items()})
    monkeypatch.setattr(oss_cli, "_call", api)
    _, out = run(["collect", "o/r"], capsys)
    lab = out["data"]["labels"]
    assert lab["count"] == 230 and lab["truncated"] is True and lab["capped"] is False and len(lab["names"]) == 150
    assert out["data"]["truncated"]["labels.names"] == {"total": 230, "shown": 150}


def test_collect_privacy_policy_one_level_below(monkeypatch, capsys):
    api = collect_api(**{"/repos/o/r/contents/docs": listing(**{"store": "dir"}),
                        "/repos/o/r/contents/docs/store": listing(**{"privacy.md": "file"})})
    monkeypatch.setattr(oss_cli, "_call", api)
    _, out = run(["collect", "o/r"], capsys)
    assert out["data"]["files"]["privacy_policy"]["where"] == "docs/store"


@pytest.mark.parametrize("n,ok", [(1, True), (400, True), (0, False), (401, False)])
def test_readme_lines_boundaries(monkeypatch, capsys, n, ok):
    monkeypatch.setattr(oss_cli, "_call", collect_api(**{"/repos/o/r/readme": b64("\n".join(str(i) for i in range(500)))}))
    rc, out = run(["collect", "o/r", "--readme-lines", str(n)], capsys)
    if ok:
        assert rc == 0 and out["data"]["readme"]["top"].count("\n") == n - 1
    else:
        assert rc == 1 and out["code"] == "bad_args" and out["next"]


def test_collect_rejects_slugs_that_could_alter_api_path(monkeypatch, capsys):
    monkeypatch.setattr(oss_cli, "_call", collect_api())
    for bad in ("not-a-slug", "o/r/extra", "o/..", "o/r?x=1", "o/r#f"):
        rc, out = run(["collect", bad], capsys)
        assert rc == 1 and out["code"] == "bad_args" and out["next"]


# ── list-repos ───────────────────────────────────────────────────────────

def _repo(i, owner="me", **kw):
    r = {"full_name": f"{owner}/r{i}", "owner": {"login": owner}, "private": False, "fork": False, "archived": False,
         "stargazers_count": i, "language": "Go", "created_at": "2026-01-01T00:00:00Z", "pushed_at": "p",
         "description": "d", "license": None}
    r.update(kw)
    return r


def _page_of(path):
    """경로의 `&page=N` (per_page 의 `page=` 와 헷갈리지 않게)."""
    return int(re.search(r"&page=(\d+)", path).group(1))


def _pages(counts, owner="me", start=0):
    """페이지별 레포 수 → /…&page=N 경로 응답."""
    out, i = {}, start
    for page, n in enumerate(counts, 1):
        out[page] = [_repo(i + k, owner) for k in range(n)]
        i += n
    return out


def _repos_api(base, query, pages, user_type="User"):
    def by_page(path, data):
        return pages.get(_page_of(path), [])
    exact = {("GET", "/users/me"): {"type": user_type}}
    return FakeAPI(exact, {f"{base}?per_page=100": by_page})


@pytest.mark.parametrize("counts,expected,capped", [
    ([99], 99, False), ([100, 0], 100, False), ([100, 1], 101, False)])
def test_list_repos_page_boundaries(monkeypatch, capsys, counts, expected, capped):
    api = _repos_api("/users/me/repos", "type=all", _pages(counts))
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["list-repos", "me", "--limit", "0"], capsys)
    assert rc == 0 and out["data"]["total_before_limit"] == expected and out["data"]["capped"] is capped


def test_list_repos_page_cap_is_reported(monkeypatch, capsys):
    api = _repos_api("/users/me/repos", "type=all", _pages([100] * 12))
    monkeypatch.setattr(oss_cli, "_call", api)
    _, out = run(["list-repos", "me", "--limit", "0"], capsys)
    assert out["data"]["pages_capped"] is True and out["data"]["capped"] is True
    assert out["data"]["total_before_limit"] == 1000


def test_list_repos_default_limit_caps_and_says_so(monkeypatch, capsys):
    monkeypatch.setattr(oss_cli, "_call", _repos_api("/users/me/repos", "type=all", _pages([100, 50])))
    _, out = run(["list-repos", "me"], capsys)
    d = out["data"]
    assert d["count"] == 100 and d["total_before_limit"] == 150 and d["capped"] is True and d["limit"] == 100
    assert d["repos"][0]["stars"] >= d["repos"][-1]["stars"] and "잘림" in out["summary"]


def test_list_repos_owner_filter_reports_other_owners(monkeypatch, capsys):
    pages = {1: [_repo(1, "me"), _repo(2, "me"), _repo(3, "TEAM-X"), _repo(4, "freeMates")]}
    monkeypatch.setattr(oss_cli, "_call", _repos_api("/users/me/repos", "type=all", pages))
    _, out = run(["list-repos", "me"], capsys)
    d = out["data"]
    assert {r["repo"] for r in d["repos"]} == {"me/r1", "me/r2"}
    assert d["other_owner_count"] == 2 and d["other_owners"] == ["TEAM-X", "freeMates"]
    assert d["by_owner"] == {"me": 2} and d["repos"][0]["owner"] == "me" and d["repos"][0]["created_at"]
    _, out2 = run(["list-repos", "me", "--include-other-owners"], capsys)
    assert out2["data"]["count"] == 4 and out2["data"]["by_owner"] == {"me": 2, "TEAM-X": 1, "freeMates": 1}


def test_list_repos_org_uses_org_endpoint_and_include_all(monkeypatch, capsys):
    pages = {1: [_repo(1, "me"), _repo(2, "me", fork=True), _repo(3, "me", private=True), _repo(4, "me", archived=True)]}
    api = FakeAPI({("GET", "/users/me"): {"type": "Organization"}},
                  {"/orgs/me/repos?per_page=100": lambda p, d: pages.get(_page_of(p), [])})
    monkeypatch.setattr(oss_cli, "_call", api)
    _, out = run(["list-repos", "me"], capsys)
    assert out["data"]["count"] == 1
    _, out_all = run(["list-repos", "me", "--include-all"], capsys)
    assert out_all["data"]["count"] == 4


def test_list_repos_without_owner_uses_user_repos(monkeypatch, capsys):
    api = FakeAPI({}, {"/user/repos?per_page=100": lambda p, d: _pages([3]).get(_page_of(p), [])})
    monkeypatch.setattr(oss_cli, "_call", api)
    _, out = run(["list-repos"], capsys)
    assert out["data"]["count"] == 3 and out["data"]["other_owner_count"] == 0


def test_list_repos_errors_always_have_next(monkeypatch, capsys):
    for err in (api_err(404), api_err(401), gh.GitHubNetworkError("x")):
        monkeypatch.setattr(oss_cli, "_call", FakeAPI({("GET", "/users/nobody"): err}))
        rc, out = run(["list-repos", "nobody"], capsys)
        assert rc == 1 and out["ok"] is False and out["next"]


# ── local-facts (실제 git) ───────────────────────────────────────────────

def _git(root, *a, check=True):
    return subprocess.run(["git", "-C", str(root), *a], check=check, capture_output=True, text=True)


def _init(root):
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")


def _commit(root, files: dict, msg="c"):
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)


def local_facts(path, capsys, commits=50):
    rc = oss_cli.cmd_local_facts(argparse.Namespace(path=str(path), commits=commits))
    return rc, json.loads(capsys.readouterr().out)


def test_local_facts_on_real_git_repo(tmp_path, capsys):
    _init(tmp_path)
    _commit(tmp_path, {"a.py": 'x = "한글 문구"\n', ".env": "K=v\n"}, "init")
    rc, out = local_facts(tmp_path, capsys)
    assert rc == 0
    assert out["data"]["committed_secret_paths"] == [".env"]
    assert out["data"]["natural_language_strings"]["total"] == 1
    assert out["data"]["co_change"]["commits"] == 1
    assert "data.committed_secret_paths" in out["untrusted"]


def test_co_change_keeps_korean_filenames_readable(tmp_path, capsys):
    _init(tmp_path)
    _commit(tmp_path, {"한글.py": "1\n", "b.py": "1\n"}, "one")
    _commit(tmp_path, {"한글.py": "2\n", "b.py": "2\n"}, "two")
    _, out = local_facts(tmp_path, capsys)
    pair = out["data"]["co_change"]["top_pairs"][0]
    assert (pair["a"], pair["b"], pair["count"]) == ("b.py", "한글.py", 2)  # 8진수 이스케이프가 아니다
    assert '\\355' not in json.dumps(out, ensure_ascii=False)


def test_local_facts_accepts_subdirectory_of_repo(tmp_path, capsys):
    _init(tmp_path)
    _commit(tmp_path, {"sub/a.py": 'x = "안녕"\n', "top.py": "1\n"})
    rc, out = local_facts(tmp_path / "sub", capsys)
    assert rc == 0 and out["data"]["tracked_files"] == 2 and Path(out["data"]["root"]) == tmp_path.resolve()


def test_local_facts_not_a_repo_and_not_a_dir(tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()
    rc, out = local_facts(plain, capsys)
    assert rc == 1 and out["code"] == "not_a_git_repo" and out["next"]
    rc, out = local_facts(tmp_path / "missing", capsys)
    assert rc == 1 and out["code"] == "not_a_git_repo" and out["next"]


def test_local_facts_empty_repo_is_zero_commits_not_error(tmp_path, capsys):
    _init(tmp_path)
    rc, out = local_facts(tmp_path, capsys)
    assert rc == 0 and out["data"]["co_change"]["commits"] == 0 and out["data"]["git_error"] is None


def test_git_failure_is_distinguished_from_no_commits(tmp_path, capsys, monkeypatch):
    _init(tmp_path)
    _commit(tmp_path, {"a.py": "1\n"})
    real = oss_cli._git_raw

    def flaky(root, *args, **kw):
        if args and args[0] == "log":
            return 128, "", "fatal: something broke"
        return real(root, *args, **kw)
    monkeypatch.setattr(oss_cli, "_git_raw", flaky)
    rc, out = local_facts(tmp_path, capsys)
    assert rc == 0 and out["data"]["git_error"] == {"log": "fatal: something broke"}
    assert "git log 오류" in out["summary"]


@pytest.mark.skipif(os.name == "nt", reason="심볼릭 링크·셸 명령 샘플은 POSIX 전용")
def test_malicious_git_config_does_not_run_commands(tmp_path, capsys):
    """악성 .git/config 의 core.fsmonitor 가 ls-files 에서 실행되는 것이 재현됐다 → 막혔는지."""
    repo = tmp_path / "evil"
    _init(repo)
    _commit(repo, {"a.py": "1\n"})
    marker = tmp_path / "PWNED"
    _git(repo, "config", "core.fsmonitor", f"touch {marker}; echo")
    _git(repo, "config", "core.pager", f"touch {marker}.pager; cat")
    rc, out = local_facts(repo, capsys)
    assert rc == 0 and out["data"]["tracked_files"] == 1
    assert not marker.exists() and not Path(f"{marker}.pager").exists()


@pytest.mark.skipif(os.name == "nt", reason="심볼릭 링크는 POSIX 전용")
def test_tracked_symlink_to_outside_file_is_never_read(tmp_path, capsys):
    outside = tmp_path / "outside" / "secret.txt"
    outside.parent.mkdir()
    outside.write_text("secretkey_AKIAFAKE123\nrequests\n")
    repo = tmp_path / "repo"
    _init(repo)
    _commit(repo, {"a.py": "1\n"})
    (repo / "requirements.txt").symlink_to(outside)
    (repo / "link.py").symlink_to(outside)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "links")
    rc, out = local_facts(repo, capsys)
    assert rc == 0
    assert "secretkey_AKIAFAKE123" not in json.dumps(out, ensure_ascii=False)
    assert out["data"]["skipped"]["symlinks"] >= 2
    assert "requirements.txt" in out["data"]["manifests_seen"] and out["data"]["dependency_manifests"] == {}


def test_local_facts_manifest_parsing_and_unsupported(tmp_path, capsys):
    _init(tmp_path)
    _commit(tmp_path, {"app/build.gradle": "dependencies {\n implementation 'a.b:c:1'\n}\n",
                       "ios/Podfile": "pod 'X'\n", "Package.swift": "// swift\n", "requirements.txt": "flask\n"})
    _, out = local_facts(tmp_path, capsys)
    d = out["data"]
    assert d["dependency_manifests"]["app/build.gradle"] == ["a.b:c"]
    assert set(d["unsupported_manifests"]) == {"ios/Podfile", "Package.swift"}
    assert set(d["manifests_seen"]) == {"app/build.gradle", "requirements.txt"}


def test_local_facts_excludes_tests_and_bulk_commits(tmp_path, capsys):
    _init(tmp_path)
    _commit(tmp_path, {"src/a.py": 'm = "문구"\n', "tests/test_a.py": 'm = "테스트"\n', **{f"bulk/f{i}.py": "1\n" for i in range(35)}})
    _, out = local_facts(tmp_path, capsys)
    d = out["data"]
    assert d["natural_language_strings"]["total"] == 1 and d["natural_language_strings"]["excluded_test_files"] == 1
    assert d["co_change"]["excluded"]["large_commits"] == 1


def test_local_facts_read_caps_are_reported(tmp_path, capsys, monkeypatch):
    _init(tmp_path)
    _commit(tmp_path, {f"s{i}.py": "x = 1\n" for i in range(5)})
    monkeypatch.setattr(oss_cli, "MAX_SOURCE_FILES", 3)
    # _Budget 기본값은 정의 시점에 묶이므로 생성자를 교체해 상한을 낮춘다
    real = oss_cli._Budget
    monkeypatch.setattr(oss_cli, "_Budget", lambda: real(max_files=3))
    rc, out = local_facts(tmp_path, capsys)
    assert rc == 0 and out["data"]["capped"]["files"] is True and "capped" in out["summary"]


@pytest.mark.parametrize("value", ["0", "1001", "-5", "abc"])
def test_commits_out_of_range_is_bad_args(capsys, value, tmp_path):
    rc, out = run(["local-facts", str(tmp_path), "--commits", value], capsys)
    assert rc == 1 and out["code"] == "bad_args" and out["next"]


def test_commits_bounds_are_accepted(tmp_path, capsys):
    _init(tmp_path)
    _commit(tmp_path, {"a.py": "1\n"})
    for n in ("1", "1000"):
        rc, out = run(["local-facts", str(tmp_path), "--commits", n], capsys)
        assert rc == 0


def test_gitfile_pointing_nowhere_is_rejected(tmp_path, capsys):
    _init(tmp_path / "real")
    _commit(tmp_path / "real", {"a.py": "1\n"})
    ok, target = oss_cli._gitfile_target(tmp_path / "real")
    assert ok is True and target is None  # .git 이 디렉터리면 해당 없음
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / ".git").write_text("gitdir: /nonexistent/elsewhere\n")
    ok, _ = oss_cli._gitfile_target(fake)
    assert ok is False


def test_safe_git_flags_are_applied_to_every_call():
    assert "core.fsmonitor=false" in oss_cli._GIT_SAFE and "core.quotepath=false" in oss_cli._GIT_SAFE
    env = oss_cli._git_env()
    assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_OPTIONAL_LOCKS"] == "0" and env["GIT_TERMINAL_PROMPT"] == "0"


# ── repo-update ──────────────────────────────────────────────────────────

def _write_api(topics=("a",), desc="old", homepage="", discussions=False, **extra):
    state = {"description": desc, "homepage": homepage, "topics": list(topics), "has_discussions": discussions}
    calls = []

    def meta(path, data):
        return repo_meta(description=state["description"], homepage=state["homepage"],
                         has_discussions=state["has_discussions"], topics=state["topics"])

    def patch(path, data):
        for k, v in data.items():
            state[k] = v
        return {}

    def put_topics(path, data):
        state["topics"] = data["names"]
        return {"names": data["names"]}

    api = FakeAPI({("GET", "/repos/o/r"): meta, ("GET", "/repos/o/r/topics"): lambda p, d: {"names": state["topics"]},
                   ("PATCH", "/repos/o/r"): patch, ("PUT", "/repos/o/r/topics"): put_topics, **extra})
    return api, state


def test_repo_update_dry_run_writes_nothing(monkeypatch, capsys):
    api, state = _write_api()
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["repo-update", "o/r", "--description", "new", "--topics", "b,c", "--discussions", "on", "--dry-run"], capsys)
    d = out["data"]
    assert rc == 0 and d["dry_run"] is True and "승인" in out["next"]
    assert d["before"]["topics"] == ["a"] and d["planned"]["topics"] == ["a", "b", "c"]  # 기본은 합집합
    assert d["planned"]["description"] == "new" and d["planned"]["has_discussions"] is True and "after" not in d
    assert [c[0] for c in api.calls] == ["GET", "GET"] and state["description"] == "old"


def test_repo_update_applies_and_reports_before_after(monkeypatch, capsys):
    api, state = _write_api()
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["repo-update", "o/r", "--description", "new", "--homepage", "https://x.dev", "--topics", "b", "--discussions", "on"], capsys)
    d = out["data"]
    assert rc == 0 and d["before"]["description"] == "old" and d["after"]["description"] == "new"
    assert d["after"]["topics"] == ["a", "b"] and d["after"]["has_discussions"] is True and d["warnings"] == []
    methods = [(c[0], c[1]) for c in api.calls if c[0] != "GET"]
    assert ("PATCH", "/repos/o/r") in methods and ("PUT", "/repos/o/r/topics") in methods


def test_repo_update_topics_replace_vs_add(monkeypatch, capsys):
    api, _ = _write_api(topics=("a", "b"))
    monkeypatch.setattr(oss_cli, "_call", api)
    _, out = run(["repo-update", "o/r", "--topics", "c", "--topics-mode", "replace", "--dry-run"], capsys)
    assert out["data"]["planned"]["topics"] == ["c"]
    _, out = run(["repo-update", "o/r", "--topics", "c,A", "--dry-run"], capsys)
    assert out["data"]["planned"]["topics"] == ["a", "b", "c"]  # 대문자는 소문자로, 중복은 합친다


def test_repo_update_no_change_and_nothing_to_change(monkeypatch, capsys):
    api, _ = _write_api(desc="same")
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["repo-update", "o/r", "--description", "same"], capsys)
    assert rc == 0 and out["code"] == "no_change" and not any(c[0] != "GET" for c in api.calls)
    rc, out = run(["repo-update", "o/r"], capsys)
    assert rc == 1 and out["code"] == "nothing_to_change" and out["next"]


@pytest.mark.parametrize("argv,needle", [
    (["--topics", "Bad_Topic"], "토픽"),
    (["--topics", ",".join(f"t{i}" for i in range(25))], "20개"),
    (["--topics", "x" * 51], "토픽"),
    (["--description", "가" * 351], "350"),
    (["--homepage", "not a url"], "homepage"),
])
def test_repo_update_validation_failures_do_not_write(monkeypatch, capsys, argv, needle):
    api, _ = _write_api(topics=())
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["repo-update", "o/r", *argv], capsys)
    assert rc == 1 and out["code"] == "invalid_input" and needle in out["summary"] and out["next"]
    assert not any(c[0] != "GET" for c in api.calls)


def test_repo_update_partial_failure_reports_before_and_applied(monkeypatch, capsys):
    api, _ = _write_api(**{})
    api.exact[("PUT", "/repos/o/r/topics")] = api_err(422, "bad topics")
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["repo-update", "o/r", "--description", "new", "--topics", "b"], capsys)
    assert rc == 1 and out["applied"] == ["description"] and out["before"]["description"] == "old" and out["next"]


def test_repo_update_warns_when_discussions_not_applied(monkeypatch, capsys):
    api, state = _write_api()
    api.exact[("PATCH", "/repos/o/r")] = lambda p, d: {}  # 무시하는 서버
    monkeypatch.setattr(oss_cli, "_call", api)
    _, out = run(["repo-update", "o/r", "--discussions", "on"], capsys)
    assert out["data"]["warnings"] and "has_discussions" in out["data"]["warnings"][0]


def test_repo_update_has_no_destructive_options():
    parser = oss_cli.build_parser()
    sub = parser._subparsers._group_actions[0].choices["repo-update"]
    opts = {o for a in sub._actions for o in a.option_strings}
    assert opts >= {"--description", "--homepage", "--topics", "--discussions", "--dry-run"}
    for forbidden in ("--private", "--visibility", "--delete", "--archive", "--rename", "--default-branch", "--public"):
        assert forbidden not in opts


# ── label ────────────────────────────────────────────────────────────────

def _label_api(existing=None):
    rows = existing if existing is not None else [{"name": "bug", "color": "d73a4a", "description": ""},
                                                   {"name": "작업중", "color": "ffffff", "description": ""}]
    return FakeAPI({("GET", "/repos/o/r/labels?per_page=100&page=1"): rows,
                    ("POST", "/repos/o/r/labels"): lambda p, d: {"name": d["name"], "color": d["color"], "description": d.get("description")},
                    ("PATCH", "/repos/o/r/labels/bug"): lambda p, d: {"name": d.get("new_name", "bug"), "color": d.get("color", "d73a4a"), "description": ""}})


def test_label_create_rename_recolor(monkeypatch, capsys):
    api = _label_api()
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["label", "o/r", "create", "--name", "good first issue", "--color", "#7057FF", "--description", "쉬운 이슈"], capsys)
    assert rc == 0 and out["data"]["after"]["color"] == "7057ff" and out["data"]["before"] is None
    rc, out = run(["label", "o/r", "rename", "--name", "bug", "--new-name", "type: bug"], capsys)
    assert rc == 0 and out["data"]["before"]["name"] == "bug" and out["data"]["after"]["name"] == "type: bug"
    assert ("PATCH", "/repos/o/r/labels/bug", {"new_name": "type: bug"}) in api.calls  # 새 이름으로 PATCH — 이슈의 라벨은 유지된다
    rc, out = run(["label", "o/r", "recolor", "--name", "bug", "--color", "00ff00"], capsys)
    assert rc == 0 and ("PATCH", "/repos/o/r/labels/bug", {"color": "00ff00"}) in api.calls


def test_label_dry_run_writes_nothing(monkeypatch, capsys):
    api = _label_api()
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["label", "o/r", "rename", "--name", "bug", "--new-name", "x", "--dry-run"], capsys)
    assert rc == 0 and out["data"]["dry_run"] is True and out["data"]["planned"]["method"] == "PATCH"
    assert not any(c[0] != "GET" for c in api.calls)


@pytest.mark.parametrize("action,extra", [("rename", ["--new-name", "x"]), ("recolor", ["--color", "000000"])])
def test_label_protected_status_labels_are_refused_in_code(monkeypatch, capsys, action, extra):
    api = _label_api()
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["label", "o/r", action, "--name", "작업중", *extra], capsys)
    assert rc == 1 and out["code"] == "protected_label" and out["next"] and api.calls == []  # API 조차 부르지 않는다


def test_label_rename_into_protected_name_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(oss_cli, "_call", _label_api())
    rc, out = run(["label", "o/r", "rename", "--name", "bug", "--new-name", "작업완료"], capsys)
    assert rc == 1 and out["code"] == "protected_label"


def test_label_conflicts_and_missing(monkeypatch, capsys):
    api = _label_api([{"name": "bug", "color": "x", "description": ""}, {"name": "Feature", "color": "x", "description": ""}])
    monkeypatch.setattr(oss_cli, "_call", api)
    _, out = run(["label", "o/r", "create", "--name", "BUG"], capsys)  # 라벨 이름은 대소문자 무관
    assert out["code"] == "label_exists" and out["before"]["name"] == "bug"
    _, out = run(["label", "o/r", "rename", "--name", "bug", "--new-name", "feature"], capsys)
    assert out["code"] == "label_exists"
    _, out = run(["label", "o/r", "rename", "--name", "ghost", "--new-name", "x"], capsys)
    assert out["code"] == "label_not_found" and out["next"]
    assert not any(c[0] != "GET" for c in api.calls)


def test_label_case_only_rename_is_allowed(monkeypatch, capsys):
    api = _label_api()
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["label", "o/r", "rename", "--name", "bug", "--new-name", "Bug", "--dry-run"], capsys)
    assert rc == 0


@pytest.mark.parametrize("argv", [["create"], ["rename", "--name", "a"], ["recolor", "--name", "a"],
                                  ["create", "--name", "a", "--color", "zzz"],
                                  ["create", "--name", "a", "--description", "x" * 101]])
def test_label_input_validation(monkeypatch, capsys, argv):
    monkeypatch.setattr(oss_cli, "_call", _label_api())
    rc, out = run(["label", "o/r", *argv], capsys)
    assert rc == 1 and out["code"] == "invalid_input" and out["next"]


def test_label_has_no_delete_action(capsys):
    rc, out = run(["label", "o/r", "delete", "--name", "bug"], capsys)
    assert rc == 1 and out["code"] == "bad_args" and out["next"]
    assert "delete" not in oss_cli.build_parser()._subparsers._group_actions[0].choices["label"]._actions[2].choices


# ── 계약: next·PAT·판정 금지 ─────────────────────────────────────────────

def test_bad_target_is_json_error(capsys):
    rc = oss_cli.run_cli(oss_cli.build_parser(), ["collect", "not-a-slug"])
    assert rc == 1
    assert '"code": "bad_args"' in capsys.readouterr().out


def test_every_error_json_has_a_next(monkeypatch, capsys, tmp_path):
    scenarios = []
    scenarios.append((["collect", "bad"], None))
    scenarios.append((["collect"], None))                                   # argparse 오류
    scenarios.append((["nope"], None))
    scenarios.append((["local-facts", str(tmp_path)], None))                # not_a_git_repo
    scenarios.append((["repo-update", "o/r"], collect_api()))               # nothing_to_change
    scenarios.append((["collect", "o/r"], FakeAPI({("GET", "/repos/o/r"): api_err(500, "boom")})))
    scenarios.append((["collect", "o/r"], FakeAPI({("GET", "/repos/o/r"): gh.GitHubNetworkError("x")})))
    scenarios.append((["label", "o/r", "rename", "--name", "작업중", "--new-name", "x"], _label_api()))
    for argv, api in scenarios:
        if api is not None:
            monkeypatch.setattr(oss_cli, "_call", api)
        rc, out = run(argv, capsys)
        assert rc == 1 and out["ok"] is False, argv
        assert out.get("next"), f"next 가 비었다: {argv} -> {out}"
    monkeypatch.setattr(oss_cli, "_pat", lambda o, r: None)
    rc, out = run(["collect", "o/r"], capsys)
    assert out["code"] == "no_pat" and out["next"]
    rc, out = run(["list-repos"], capsys)
    assert out["code"] == "no_pat" and out["next"]


def test_unexpected_exception_becomes_json_with_next(monkeypatch, capsys):
    def boom(args):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(oss_cli, "cmd_collect", boom)
    rc, out = run(["collect", "o/r"], capsys)
    assert rc == 1 and out["code"] == "handler_error" and "kaboom" in out["summary"] and out["next"]


def test_pat_never_appears_in_any_output(monkeypatch, capsys, tmp_path):
    leaky = api_err(500, f"Bad credentials {PAT} leaked")
    outputs = []
    for argv, api in [
        (["collect", "o/r"], FakeAPI({("GET", "/repos/o/r"): leaky})),
        (["collect", "o/r"], collect_api(**{"/repos/o/r/issues": leaky})),
        (["list-repos", "me"], FakeAPI({("GET", "/users/me"): leaky})),
        (["repo-update", "o/r", "--description", "x"], FakeAPI({("GET", "/repos/o/r"): leaky})),
        (["label", "o/r", "create", "--name", "a"], FakeAPI({("GET", "/repos/o/r/labels?per_page=100&page=1"): leaky})),
        (["collect", "o/r"], collect_api()),
    ]:
        monkeypatch.setattr(oss_cli, "_call", api)
        run(argv, capsys)
    _init(tmp_path)
    _commit(tmp_path, {"a.py": "1\n"})
    local_facts(tmp_path, capsys)
    # 위 호출의 출력은 run()/local_facts() 가 소비했으므로, 다시 한 번 수집해 직접 검사한다
    monkeypatch.setattr(oss_cli, "_call", FakeAPI({("GET", "/repos/o/r"): leaky}))
    oss_cli.run_cli(oss_cli.build_parser(), ["collect", "o/r"])
    text = capsys.readouterr().out
    assert PAT not in text and "***" in text


def test_get_output_path_uses_cwd_of_work_repo(tmp_path, capsys, monkeypatch):
    _init(tmp_path)
    monkeypatch.chdir(Path(__file__).resolve().parent)  # 스크립트 쪽 cwd 를 흉내
    rc, out = run(["get-output-path", "oss-consult", "--title", "T 컨설팅", "--cwd", str(tmp_path)], capsys)
    # 스크립트 폴더가 아니라 --cwd 로 지정한 작업 레포 기준으로 경로가 계산된다
    assert rc == 0 and Path(out["path"]).resolve().is_relative_to(tmp_path.resolve()) and out["next"]
    assert out["path"].endswith("T_컨설팅.md") and "oss-consult" in out["path"]
    rc, out = run(["get-output-path", "oss-consult", "--cwd", str(tmp_path / "nope")], capsys)
    assert rc == 1 and out["code"] == "bad_args" and out["next"]


def test_get_output_path_outside_git_has_next(tmp_path, capsys, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    rc, out = run(["get-output-path", "oss-consult", "--cwd", str(plain)], capsys)
    assert rc == 1 and out["code"] == "git_not_found" and out["next"]


# ── 교차 검수 반영 (#660): 출력 정리, 삭제성 write 차단 ───────────────────

def test_sanitize_clips_long_strings_and_strips_bidi_controls():
    stats = {"clipped_strings": 0, "control_chars_removed": 0}
    out = oss_cli._sanitize({"a": "x" * 5000, "top": "y" * 5000, "b": ["‮evil​.py"]}, stats)
    assert len(out["a"]) == oss_cli._STR_LIMIT + 1 and out["a"].endswith("…")   # 일반 문자열은 500자
    assert len(out["top"]) == 5000                                               # README 앞부분은 길게 허용
    assert out["b"] == ["evil.py"] and stats["control_chars_removed"] == 2 and stats["clipped_strings"] == 1


def test_collect_output_is_bounded_against_hostile_strings(monkeypatch, capsys):
    hostile = "A" * 50000
    api = collect_api(**{"/repos/o/r/labels": [{"name": hostile, "color": "d73a4a", "description": ""}]})
    api.exact[("GET", "/repos/o/r")] = repo_meta(description=hostile + "‮", homepage="https://x.dev/" + hostile)
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["collect", "o/r"], capsys)
    text = json.dumps(out, ensure_ascii=False)
    assert rc == 0 and len(text) < 40000                     # 50KB 문자열이 그대로 나오지 않는다
    assert out["data"]["sanitized"]["clipped_strings"] >= 2 and out["data"]["sanitized"]["control_chars_removed"] >= 1
    assert "‮" not in text


def test_untrusted_covers_latest_stable():
    assert "data.releases.latest_stable" in oss_cli._COLLECT_UNTRUSTED


@pytest.mark.parametrize("argv", [
    ["--description", "  "],
    ["--homepage", ""],
    ["--topics", "", "--topics-mode", "replace"],
])
def test_repo_update_refuses_clearing_values(monkeypatch, capsys, argv):
    api, _ = _write_api(topics=("a",), desc="old", homepage="https://x.dev")
    monkeypatch.setattr(oss_cli, "_call", api)
    rc, out = run(["repo-update", "o/r", *argv], capsys)
    assert rc == 1 and out["code"] == "invalid_input" and "지원하지 않는다" in out["summary"] and out["next"]
    assert not any(c[0] != "GET" for c in api.calls)
