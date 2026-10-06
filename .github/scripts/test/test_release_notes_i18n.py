"""릴리스 노트 생성기 다국어 (#793).

영문 레포의 체인지로그에 한국어 카테고리(`새 기능`)가 섞이던 문제의 회귀 방지.
한국어 출력은 이관 전과 바이트 동일해야 한다 (골든).
"""
import os
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).parent / "golden"
sys.path.insert(0, str(SCRIPTS / "changelog_providers"))
sys.path.insert(0, str(SCRIPTS))

import _common  # noqa: E402
import copilot  # noqa: E402
import github_ai  # noqa: E402
import openai_compatible  # noqa: E402
import pr_summary_comment  # noqa: E402

HANGUL = re.compile(r"[가-힣]")

KO_COMMITS = [
    "로그인 개선 : feat : 소셜 로그인 추가", "feat: 다크 모드", "결제 수정 : fix : 중복 청구 해결",
    "docs: 문서 갱신", "refactor: 구조 정리", "잡다한 변경",
]
EN_COMMITS = [
    "Login : feat : add social login", "feat: dark mode", "Billing : fix : duplicate charge",
    "docs: update guide", "refactor: tidy structure", "misc change",
]


def golden(name):
    return (GOLDEN / name).read_text(encoding="utf-8")


def test_ko_body_is_byte_identical(tmp_path):
    out = tmp_path / "b.md"
    _common.write_pr_body(_common.sections_to_markdown(_common.classify(KO_COMMITS)), str(out), lang="ko")
    assert out.read_text(encoding="utf-8") == golden("release_notes_body_ko.md")


def test_en_body_has_no_hangul(tmp_path):
    out = tmp_path / "b.md"
    md = _common.sections_to_markdown(_common.classify(EN_COMMITS), lang="en")
    _common.write_pr_body(md, str(out), lang="en")
    body = out.read_text(encoding="utf-8")
    assert not HANGUL.search(body)
    assert "* **New features**" in body and "* **Bug fixes**" in body
    assert "## Release notes" in body
    assert "## Summary by CodeRabbit" in body  # 불변 계약은 번역하지 않는다


def test_default_language_follows_repo_language(monkeypatch):
    monkeypatch.setenv("REPO_LANG", "en")
    assert "**New features**" in _common.sections_to_markdown(_common.classify(EN_COMMITS))
    monkeypatch.setenv("REPO_LANG", "ko")
    assert "**새 기능**" in _common.sections_to_markdown(_common.classify(KO_COMMITS))


def test_empty_fallback(monkeypatch):
    assert _common.empty_notes("ko") == golden("release_notes_empty_ko.md")
    assert not HANGUL.search(_common.empty_notes("en"))


def test_ko_prompts_are_byte_identical():
    assert copilot.build_prompt("{commits}", "ko") == golden("release_notes_prompt_copilot_ko.txt")
    assert openai_compatible.build_prompt("{commits}", "ko") == golden("release_notes_prompt_openai_ko.txt")
    assert github_ai.build_prompt("{commits}", "ko") == golden("release_notes_prompt_openai_ko.txt")


@pytest.mark.parametrize("builder", [copilot.build_prompt, openai_compatible.build_prompt, github_ai.build_prompt])
def test_en_prompts_have_no_hangul_and_name_english_sections(builder):
    text = builder("abc", "en")
    assert not HANGUL.search(text)
    assert "abc" in text
    assert "New features" in text


def test_prompt_survives_braces_in_commits():
    assert "{x}" in copilot.build_prompt("fix {x}", "en")


@pytest.mark.parametrize("heading", ["릴리스 노트", "Release notes", "リリースノート"])
def test_extract_body_accepts_any_language_heading(heading):
    raw = f"<!-- a -->\n\n## Summary by CodeRabbit\n\n## {heading}\n\n* **X**\n  * item\n\n<!-- end -->\n"
    assert pr_summary_comment.extract_body(raw) == "* **X**\n  * item"


def test_extract_body_still_returns_raw_without_structure():
    assert pr_summary_comment.extract_body("plain text") == "plain text"
