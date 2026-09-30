"""oss_cli 순수 함수 — 판정 없이 사실만 내는지 확인한다 (#644)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_CLI = Path(__file__).resolve().parents[1] / "scripts" / "oss_cli.py"
_spec = importlib.util.spec_from_file_location("oss_cli", _CLI)
oss_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oss_cli)


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


def test_detect_files_checks_three_places_and_flags_license_folder():
    root = {"LICENSE": "dir", "README.md": "file", "docs": "dir"}
    gh = {"CONTRIBUTING.md": "file", "ISSUE_TEMPLATE": "dir"}
    docs = {"SECURITY.md": "file"}
    f = oss_cli.detect_files(root, gh, docs, ["bug.yml", "feature.yml", "config.yml"])
    assert f["contributing"]["where"] == ".github"
    assert f["security"]["where"] == "docs"
    assert "warning" in f["license"]  # 폴더 LICENSE는 GitHub이 인식하지 못한다
    assert f["issue_templates"] == {"forms_yml": 2, "markdown": 0, "config_yml": True}
    assert f["code_of_conduct"] is None
    assert f["docs_dir"] is True


def test_labels_are_passed_through_without_classification():
    out = oss_cli.summarize_labels(["type: bug", "good first issue", "작업중"])
    assert out == {"count": 3, "names": ["type: bug", "good first issue", "작업중"]}


def test_bad_target_is_json_error(capsys):
    rc = oss_cli.run_cli(oss_cli.build_parser(), ["collect", "not-a-slug"])
    assert rc == 1
    assert '"code": "bad_args"' in capsys.readouterr().out
