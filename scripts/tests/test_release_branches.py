# scripts/tests/test_release_branches.py
"""changelog_cli의 릴리스 브랜치·provider 읽기 테스트 (#456).

head = deploy_branch(폴백 develop), base = default_branch(폴백 main),
changelog provider = options.changelog.provider(폴백 commit — #566 에서 기본 사다리가 바뀌었다).
version.yml을 정규식으로만 읽어(폐쇄망·yaml 무의존) SSOT에서 브랜치를 해석함을 검증한다.
"""
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CLI_PATH = _ROOT / "skills" / "pro-changelog-deploy" / "scripts" / "changelog_cli.py"
_spec = importlib.util.spec_from_file_location("changelog_cli", _CLI_PATH)
changelog_cli = importlib.util.module_from_spec(_spec)
sys.modules["changelog_cli"] = changelog_cli
_spec.loader.exec_module(changelog_cli)

_read_branches = changelog_cli._read_release_branches


def _write_vy(tmp_path, body):
    (tmp_path / "version.yml").write_text(body, encoding="utf-8")
    return tmp_path


def test_reads_deploy_and_default_branch(tmp_path):
    _write_vy(tmp_path, 'version: "1.0.0"\nmetadata:\n  default_branch: "trunk"\n  deploy_branch: "release"\n')
    b = _read_branches(tmp_path)
    assert b["head"] == "release"   # deploy_branch
    assert b["base"] == "trunk"     # default_branch


def test_falls_back_to_develop_main(tmp_path):
    # deploy_branch·default_branch 둘 다 없으면 develop→main 폴백
    _write_vy(tmp_path, 'version: "1.0.0"\nmetadata:\n  last_updated: "x"\n')
    b = _read_branches(tmp_path)
    assert b["head"] == "develop"
    assert b["base"] == "main"


def test_default_branch_only(tmp_path):
    # default_branch만 있으면 base는 그 값, head는 develop 폴백
    _write_vy(tmp_path, 'version: "1.0.0"\nmetadata:\n  default_branch: "main"\n')
    b = _read_branches(tmp_path)
    assert b["head"] == "develop"
    assert b["base"] == "main"


def test_reads_changelog_provider(tmp_path):
    _write_vy(tmp_path,
              'version: "1.0.0"\nmetadata:\n  template:\n    options:\n      changelog:\n        provider: "commit"\n')
    b = _read_branches(tmp_path)
    assert b["provider"] == "commit"


def test_provider_fallback_is_commit(tmp_path):
    """폴백은 commit 이다. #566 이후 기본 사다리가 commit 이라, coderabbit 으로 두면
    이 스킬만 'CodeRabbit 을 기다리는 레포'로 잘못 판정한다."""
    _write_vy(tmp_path, 'version: "1.0.0"\nmetadata:\n  default_branch: "main"\n')
    b = _read_branches(tmp_path)
    assert b["provider"] == "commit"


def test_no_version_yml_all_fallback(tmp_path):
    b = _read_branches(tmp_path)
    assert b == {"head": "develop", "base": "main", "provider": "commit"}


# ── #842: 정본은 version.yml, config 전역 키는 읽지 않는다 ─────────────────────
import json
import subprocess


def _detect(tmp_path, config, owner="o", repo="r"):
    """detect-release-context 를 실제 CLI 로 부른다. config 는 tmp 파일로 넘겨 사용자 config 를 건드리지 않는다."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(config), encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(_CLI_PATH), "detect-release-context",
         "--project-root", str(tmp_path), "--owner", owner, "--repo", repo, "--config", str(cfg)],
        capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(out.stdout)


def _cfg(global_cd=None, repo_cd=None):
    repo_entry = {"owner": "o", "repo": "r"}
    if repo_cd is not None:
        repo_entry["changelog_deploy"] = repo_cd
    return {"github": {"changelog_deploy": global_cd or {}, "repos": [repo_entry]}}


def test_global_branch_keys_are_ignored(tmp_path):
    """전역 키가 version.yml 을 덮어쓰던 것이 #842 의 원인이다. 읽지 않고 남아 있다고만 알린다."""
    _write_vy(tmp_path, 'version: "1.0.0"\nmetadata:\n  default_branch: "trunk"\n  deploy_branch: "release"\n')
    d = _detect(tmp_path, _cfg(global_cd={"head_branch": "develop", "base_branch": "main",
                                          "provider": "gemini", "auto_approve": True}))
    assert d["branches"]["head"] == "release"
    assert d["branches"]["base"] == "trunk"
    assert d["branches"]["provider"] == "commit"
    assert d["branches_source"] == "version.yml"
    assert d["conflict"] == []
    assert d["config"]["ignored_global_keys"] == ["base_branch", "head_branch", "provider"]


def test_global_keys_ignored_without_version_yml(tmp_path):
    """version.yml 이 없어도 전역 키는 쓰지 않는다 — 다른 레포의 지식이기 때문이다."""
    d = _detect(tmp_path, _cfg(global_cd={"head_branch": "dev", "base_branch": "prod"}))
    assert d["branches"] == {"head": "develop", "base": "main", "provider": "commit"}
    assert d["branches_source"] == "fallback"


def test_version_yml_wins_over_repo_config_and_reports_conflict(tmp_path):
    _write_vy(tmp_path, 'version: "1.0.0"\nmetadata:\n  default_branch: "main"\n  deploy_branch: "develop"\n')
    d = _detect(tmp_path, _cfg(repo_cd={"head_branch": "main", "base_branch": "main",
                                        "provider": "coderabbit"}))
    assert d["branches"]["head"] == "develop"          # version.yml 값
    assert d["branches_source"] == "version.yml"
    by_key = {c["key"]: c for c in d["conflict"]}
    assert set(by_key) == {"head_branch", "provider"}  # 같은 base_branch 는 충돌 아님
    assert by_key["head_branch"] == {"key": "head_branch", "version_yml": "develop",
                                     "config": "main", "version_yml_explicit": True}
    # provider 는 version.yml 에 적혀 있지 않았다 — 폴백끼리의 차이임을 agent 가 알 수 있어야 한다
    assert by_key["provider"]["version_yml_explicit"] is False


def test_no_conflict_when_repo_config_matches(tmp_path):
    _write_vy(tmp_path, 'version: "1.0.0"\nmetadata:\n  default_branch: "main"\n  deploy_branch: "develop"\n')
    d = _detect(tmp_path, _cfg(repo_cd={"head_branch": "develop", "base_branch": "main",
                                        "provider": "commit", "auto_approve": True}))
    assert d["conflict"] == []


def test_repo_config_used_only_without_version_yml(tmp_path):
    d = _detect(tmp_path, _cfg(repo_cd={"head_branch": "main", "base_branch": "deploy",
                                        "provider": "github-ai"}))
    assert d["branches_source"] == "config"
    assert d["branches"] == {"head": "main", "base": "deploy", "provider": "commit"}  # 종료값 흡수
    assert d["conflict"] == []


def test_other_repo_entry_is_not_used(tmp_path):
    d = _detect(tmp_path, _cfg(repo_cd={"head_branch": "main", "base_branch": "deploy"}),
                owner="o", repo="other")
    assert d["branches_source"] == "fallback"
    assert d["config"]["repo_entry"] is False


def test_missing_config_file_is_not_an_error(tmp_path):
    out = subprocess.run(
        [sys.executable, str(_CLI_PATH), "detect-release-context", "--project-root", str(tmp_path),
         "--owner", "o", "--repo", "r", "--config", str(tmp_path / "none.json")],
        capture_output=True, text=True, encoding="utf-8",
    )
    d = json.loads(out.stdout)
    assert d["ok"] is True
    assert d["branches_source"] == "fallback"
