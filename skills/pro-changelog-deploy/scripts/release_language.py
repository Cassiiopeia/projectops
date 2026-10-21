"""릴리스 언어: 노트 언어(워크플로우와 같은 규칙) · 노트 제목 · 스토어 언어 · 고정 스토어 문구 (#977)
정본 3곳 모두 CI 가 읽는 레포 값 (version.yml language · store_locales*, 워크플로우 env STORE_WHATS_NEW_OVERRIDE)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common.repo_language import read_team_language

# 워크플로우 카탈로그가 없는 레포용 제목 (.github/scripts/i18n/{ko,en}.json 과 같은 값 — 테스트가 대조)
BUILT_IN_HEADINGS = {
    "ko": {"heading": "릴리스 노트", "feat": "새 기능", "fix": "버그 수정",
           "improve": "개선", "docs": "문서", "etc": "기타"},
    "en": {"heading": "Release notes", "feat": "New features", "fix": "Bug fixes",
           "improve": "Improvements", "docs": "Documentation", "etc": "Other"},
}
# 카탈로그 키 > 제목 칸 이름
CATALOG_HEADING_KEYS = {"heading": "release_notes.heading", "feat": "release_notes.section.feat",
                        "fix": "release_notes.section.fix", "improve": "release_notes.section.improve",
                        "docs": "release_notes.section.docs", "etc": "release_notes.section.etc"}
# i18n.messages 와 같은 값: 파일 없으면 en, 파일은 있는데 키가 없으면 ko (기존 레포 문구 유지)
NO_VERSION_YML_LANGUAGE = "en"
NO_LANGUAGE_KEY_LANGUAGE = "ko"
STORE_LOCALE_KEYS = ("store_locales", "store_locales_ios", "store_locales_play")
# 워크플로우 env 의 고정 스토어 문구: STORE_WHATS_NEW_OVERRIDE: "..."
FIXED_WHATS_NEW_PATTERN = re.compile(r"^\s+STORE_WHATS_NEW_OVERRIDE:\s*[\"'](.*)[\"']\s*(?:#.*)?$", re.M)


def _load_headings(project_root: Path) -> dict:
    """레포 워크플로우 카탈로그(있으면) > 내장 표. 언어 > 제목 칸"""
    catalog_dir = project_root / ".github" / "scripts" / "i18n"
    headings = {}
    for catalog_file in sorted(catalog_dir.glob("*.json")) if catalog_dir.is_dir() else []:
        try:
            catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(catalog, dict) and all(key in catalog for key in CATALOG_HEADING_KEYS.values()):
            headings[catalog_file.stem] = {name: catalog[key] for name, key in CATALOG_HEADING_KEYS.items()}
    return headings or BUILT_IN_HEADINGS


def _normalize_language(value: str, supported: list[str]) -> str:
    """ko-KR · ko_KR · KO > 지원 코드. 모르면 en (i18n.messages.normalize 와 같은 규칙)"""
    code = value.strip().split(".")[0].replace("_", "-")
    by_lower = {name.lower(): name for name in supported}
    if code.lower() in by_lower:
        return by_lower[code.lower()]
    return by_lower.get(code.split("-")[0].lower(), NO_VERSION_YML_LANGUAGE)


def resolve_notes_language(project_root: Path, headings: dict) -> tuple[str, str]:
    """(노트 언어, 출처). 출처: version.yml | version.yml_default | no_version_yml"""
    if not (project_root / "version.yml").is_file():
        return NO_VERSION_YML_LANGUAGE, "no_version_yml"
    team_language = read_team_language(project_root)
    if not team_language:
        return NO_LANGUAGE_KEY_LANGUAGE, "version.yml_default"
    return _normalize_language(team_language, sorted(headings)), "version.yml"


def _read_locale_list(version_yml_text: str, key: str) -> list[str] | None:
    """options.<key> 인라인 배열 (주석 줄 제외, 적힌 표기 그대로). 키가 없으면 None"""
    for line in version_yml_text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        matched = re.match(rf"^\s+{key}:\s*\[([^\]]*)\]", line)
        if matched:
            locales = [item.strip().strip("\"'") for item in matched.group(1).split(",")]
            return list(dict.fromkeys(locale for locale in locales if locale))
    return None


def _language_of(locale: str) -> str:
    """ko-KR · zh-Hans · en_US > ko · zh · en"""
    return locale.replace("_", "-").split("-")[0].lower()


def _fixed_whats_new(project_root: Path) -> list[dict]:
    """워크플로우 env 에 고정된 스토어 문구 (빈 값 제외) > [{workflow, text}]"""
    workflow_dir = project_root / ".github" / "workflows"
    found = []
    for workflow_file in sorted(workflow_dir.glob("*.y*ml")) if workflow_dir.is_dir() else []:
        try:
            text = workflow_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for matched in FIXED_WHATS_NEW_PATTERN.finditer(text):
            if matched.group(1).strip():
                found.append({"workflow": workflow_file.name, "text": matched.group(1).strip()})
    return found


def collect_store_languages(project_root: Path, notes_language: str) -> dict:
    """스토어 언어 구성: 목록 3종 · 기본 언어 · 번역 대상 · 고정 문구"""
    version_yml = project_root / "version.yml"
    text = version_yml.read_text(encoding="utf-8", errors="replace") if version_yml.is_file() else ""
    lists = {key: _read_locale_list(text, key) for key in STORE_LOCALE_KEYS}
    all_locales = list(dict.fromkeys(locale for values in lists.values() if values for locale in values))
    base_locale = next((values[0] for values in lists.values() if values), None)
    # 노트 언어와 다른 언어 전부 (기본 언어 포함 — 노트가 기본 언어가 아니면 그것도 옮겨야 스토어에 맞는 말이 간다)
    translation_targets = [locale for locale in all_locales if _language_of(locale) != notes_language]
    return {
        "locales": lists["store_locales"], "locales_ios": lists["store_locales_ios"],
        "locales_play": lists["store_locales_play"],
        "base_locale": base_locale,
        "translation_targets": translation_targets,
        "fixed_whats_new": _fixed_whats_new(project_root),
    }


def collect_release_language(project_root: Path) -> dict:
    """detect-release-context 의 release_language 블록"""
    headings = _load_headings(project_root)
    notes_language, source = resolve_notes_language(project_root, headings)
    return {
        "notes_language": notes_language,
        "notes_language_source": source,
        "headings": headings.get(notes_language) or BUILT_IN_HEADINGS[NO_VERSION_YML_LANGUAGE],
        "store": collect_store_languages(project_root, notes_language),
    }
