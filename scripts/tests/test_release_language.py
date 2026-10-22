# scripts/tests/test_release_language.py
"""릴리스 언어 계약: 워크플로우 i18n 과 같은 언어·제목, 스토어 번역 대상, 고정 문구 (#977)."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT / "scripts", ROOT / "skills" / "pro-changelog-deploy" / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from common.repo_language import LANGUAGE_KEY_PATTERN  # noqa: E402
from release_language import (  # noqa: E402
    BUILT_IN_HEADINGS, CATALOG_HEADING_KEYS, collect_release_language)

# 워크플로우 정본(.github/scripts/i18n/messages.py) — sys.path 에 .github/scripts 를 넣지 않고 파일로 연다
_spec = importlib.util.spec_from_file_location("i18n_messages_977", ROOT / ".github" / "scripts" / "i18n" / "messages.py")
messages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(messages)


def test_내장_제목과_언어_키_패턴이_워크플로우_카탈로그와_같다():
    """카탈로그가 없는 레포에서도 워크플로우 생성기와 같은 제목을 쓰게 (드리프트 방지)."""
    for language, headings in BUILT_IN_HEADINGS.items():
        catalog = messages.load_catalog(language)
        assert headings == {name: catalog[key] for name, key in CATALOG_HEADING_KEYS.items()}, language
    assert LANGUAGE_KEY_PATTERN.pattern == messages._LANG_KEY.pattern


@pytest.mark.parametrize("version_yml", [None, "metadata:\n  version: 1\n", "options:\n  language: en\n",
                                         "options:\n  language: ko\n", "options:\n  language: \"ko-KR\"\n",
                                         "options:\n  language: ja\n"])
def test_노트_언어는_워크플로우_resolve_language_와_같다(tmp_path, version_yml):
    if version_yml is not None:
        (tmp_path / "version.yml").write_text(version_yml, encoding="utf-8")
    expected = messages.resolve_language(str(tmp_path / "version.yml"), env={})
    assert collect_release_language(tmp_path)["notes_language"] == expected


def test_노트가_기본_언어와_다르면_기본_언어도_번역하고_고정_문구를_알린다(tmp_path):
    (tmp_path / "version.yml").write_text(
        "metadata:\n  template:\n    options:\n      language: en\n"
        "      store_locales: [\"ko-KR\", \"en-US\"]\n      store_locales_play: [\"ko-KR\", \"en-US\", \"ja-JP\"]\n",
        encoding="utf-8")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "IOS.yaml").write_text(
        "env:\n  STORE_WHATS_NEW_OVERRIDE: \"Bug fixes.\"\njobs:\n  a:\n    env:\n"
        "      STORE_WHATS_NEW_OVERRIDE: ${{ env.STORE_WHATS_NEW_OVERRIDE }}\n", encoding="utf-8")
    (workflows / "PLAY.yaml").write_text("env:\n  STORE_WHATS_NEW_OVERRIDE: \"\"\n", encoding="utf-8")
    store = collect_release_language(tmp_path)["store"]
    assert store["base_locale"] == "ko-KR" and store["translation_targets"] == ["ko-KR", "ja-JP"]
    assert store["fixed_whats_new"] == [{"workflow": "IOS.yaml", "text": "Bug fixes."}]
