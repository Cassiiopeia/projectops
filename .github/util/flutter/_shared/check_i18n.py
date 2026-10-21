#!/usr/bin/env python3
"""HTML 마법사 언어 전환 검증 (#769) — check-consistency.py 가 함께 실행한다.

대상: Flutter 마법사 3종 + common 마법사 2종 (I18N_PAGES)
검사 5개: 엔진 로드 순서, 사전 JSON 형식, 키 누락(en·ko), 안 쓰는 키, HTML 본문 한글 잔존

en 원본 2곳
  - 정적 마크업: data-i18n 요소의 HTML 내용 (= 페이지 기본 영문)
  - 동적 문구 : registerWizardMessages 사전의 en
ko 는 전부 사전. 따라서 "en 사전" = HTML 추출분 ∪ 사전 en 으로 보고 대조한다.

단독 실행:
    python3 .github/util/flutter/_shared/check_i18n.py
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

SHARED_DIR = Path(__file__).resolve().parent
UTIL_DIR = SHARED_DIR.parent.parent
I18N_ENGINE = SHARED_DIR / "wizard-i18n.js"
SHARED_COMMON_JS = SHARED_DIR / "wizard-common.js"

# (표시 이름, HTML, 페이지 JS glob 접두어, 엔진 src, wizard-common.js 사용 여부)
I18N_PAGES = (
    ("testflight", UTIL_DIR / "flutter/testflight-wizard/testflight-wizard.html", "testflight-wizard", "../_shared/wizard-i18n.js", True),
    ("playstore", UTIL_DIR / "flutter/playstore-wizard/playstore-wizard.html", "playstore-wizard", "../_shared/wizard-i18n.js", True),
    ("firebase", UTIL_DIR / "flutter/firebase-wizard/firebase-wizard.html", "firebase-wizard", "../_shared/wizard-i18n.js", True),
    ("projects-sync", UTIL_DIR / "common/projects-sync-wizard/projects-sync-wizard.html", "projects-sync-wizard", "../../flutter/_shared/wizard-i18n.js", False),
    ("secrets-converter", UTIL_DIR / "common/github-secrets-converter/secrets-converter.html", "secrets-converter", "../../flutter/_shared/wizard-i18n.js", False),
)

HANGUL_RE = re.compile(r"[가-힣]")
KEY_ATTRIBUTES = ("data-i18n", "data-i18n-placeholder", "data-i18n-title")
# 키 있는 속성 > 그 키가 바꾸는 실제 속성
TRANSLATED_ATTRIBUTE_BY_KEY_ATTRIBUTE = {"data-i18n-placeholder": "placeholder", "data-i18n-title": "title"}
TRANSLATE_CALL_RE = re.compile(r"""\btranslate\(\s*['"`]([A-Za-z0-9_.-]+)['"`]""")
REGISTER_CALL_RE = re.compile(r"registerWizardMessages\(\s*(?=\{)")
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# 한글이 있어도 되는 HTML 영역: 주석, <style>(CSS 주석), 버전 이력(versionJson — 과거 기록은 원문 유지)
LANGUAGE_NEUTRAL_SCRIPT_IDS = {"versionJson"}


class TranslatableMarkupParser(HTMLParser):
    """data-i18n 요소의 원문(en)·속성 원문 수집 + 번역 대상 밖 한글 텍스트 수집"""

    def __init__(self, source: str):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.line_offsets = [0]
        for line in source.splitlines(keepends=True):
            self.line_offsets.append(self.line_offsets[-1] + len(line))
        self.open_elements: list[dict] = []
        self.english_by_key: dict[str, list[str]] = {}
        self.stray_hangul: list[str] = []
        self.inside_neutral_script = False

    def _offset(self) -> int:
        line, column = self.getpos()
        return self.line_offsets[line - 1] + column

    def _is_inside_translated_element(self) -> bool:
        return any(element["key"] or element["is_language_toggle"] for element in self.open_elements)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "style" or (tag == "script" and attributes.get("id") in LANGUAGE_NEUTRAL_SCRIPT_IDS):
            self.inside_neutral_script = True
        for key_attribute, real_attribute in TRANSLATED_ATTRIBUTE_BY_KEY_ATTRIBUTE.items():
            key = attributes.get(key_attribute)
            if key:
                self.english_by_key.setdefault(key, []).append(attributes.get(real_attribute) or "")
        for name, value in attrs:
            if value and HANGUL_RE.search(value) and name not in KEY_ATTRIBUTES:
                self.stray_hangul.append(f"{tag}[{name}]: {value.strip()[:60]}")
        if tag in VOID_TAGS:
            return
        content_start = self._offset() + len(self.get_starttag_text() or "")
        self.open_elements.append({
            "tag": tag,
            "key": attributes.get("data-i18n"),
            # 전환 버튼 라벨(한국어/English)은 엔진이 채운다
            "is_language_toggle": "data-lang-toggle" in attributes,
            "start": content_start,
        })

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and self.open_elements:
            self.open_elements.pop()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.inside_neutral_script = False
        # 같은 태그의 가장 안쪽 열린 요소까지 닫는다 (잘못 닫힌 마크업 허용)
        for index in range(len(self.open_elements) - 1, -1, -1):
            if self.open_elements[index]["tag"] == tag:
                element = self.open_elements[index]
                del self.open_elements[index:]
                if element["key"]:
                    inner_html = self.source[element["start"]:self._offset()]
                    self.english_by_key.setdefault(element["key"], []).append(inner_html.strip())
                return

    def handle_data(self, data):
        if self.inside_neutral_script or self._is_inside_translated_element():
            return
        if HANGUL_RE.search(data):
            self.stray_hangul.append(" ".join(data.split())[:60])


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_dictionaries(path: Path, problems: list[str]) -> dict[str, dict[str, str]]:
    """registerWizardMessages({...}) 블록 > {"en": {...}, "ko": {...}} (JSON 형식만 허용)"""
    merged: dict[str, dict[str, str]] = {"en": {}, "ko": {}}
    source = read_text(path)
    decoder = json.JSONDecoder()
    for match in REGISTER_CALL_RE.finditer(source):
        try:
            messages, _ = decoder.raw_decode(source, match.end())
        except json.JSONDecodeError as error:
            problems.append(f"[i18n] {path.name}: 사전이 JSON 형식이 아닙니다 ({error})")
            continue
        for language in ("en", "ko"):
            merged[language].update(messages.get(language, {}))
    return merged


def page_js_files(html_path: Path, prefix: str) -> list[Path]:
    return sorted(html_path.parent.glob(f"{prefix}*.js"))


def check_load_order(label: str, html: str, engine_src: str, prefix: str, uses_common: bool) -> list[str]:
    """엔진 > (wizard-common.js) > 사전 > 마법사 JS 순서"""
    problems = []
    engine_index = html.find(f'src="{engine_src}"')
    dictionary_index = html.find(f'src="{prefix}-i18n.js"')
    main_index = html.find(f'src="{prefix}.js"')
    if engine_index == -1:
        return [f"[{label}] 언어 엔진을 로드하지 않습니다: {engine_src}"]
    if dictionary_index == -1:
        problems.append(f"[{label}] 사전 {prefix}-i18n.js 를 로드하지 않습니다")
    elif main_index != -1 and dictionary_index > main_index:
        problems.append(f"[{label}] 사전 {prefix}-i18n.js 가 {prefix}.js 보다 늦게 로드됩니다")
    if uses_common:
        common_index = html.find('src="../_shared/wizard-common.js"')
        if common_index != -1 and engine_index > common_index:
            problems.append(f"[{label}] wizard-i18n.js 가 wizard-common.js 보다 늦게 로드됩니다")
    if "data-lang-toggle" not in html:
        problems.append(f"[{label}] 언어 전환 버튼(data-lang-toggle)이 없습니다")
    return problems


def check_page(label, html_path, prefix, engine_src, uses_common, shared_messages, shared_usage) -> list[str]:
    """페이지 1개: 로드 순서 > 키 대조(en·ko) > 안 쓰는 키 > 한글 잔존"""
    html = read_text(html_path)
    if not html:
        return [f"[{label}] {html_path.name} 이 없습니다"]
    problems = check_load_order(label, html, engine_src, prefix, uses_common)

    js_files = page_js_files(html_path, prefix)
    own_dictionary_files = [p for p in js_files if p.name.endswith("-i18n.js")]
    own_messages: dict[str, dict[str, str]] = {"en": {}, "ko": {}}
    for path in own_dictionary_files:
        parsed = parse_dictionaries(path, problems)
        for language in ("en", "ko"):
            own_messages[language].update(parsed[language])

    parser = TranslatableMarkupParser(html)
    parser.feed(html)
    html_keys = set(parser.english_by_key)
    code_sources = [read_text(p) for p in js_files if p not in own_dictionary_files]
    if uses_common:
        code_sources.append(read_text(SHARED_COMMON_JS))
    code_keys = {key for source in code_sources for key in TRANSLATE_CALL_RE.findall(source)}

    english = {**shared_messages["en"], **own_messages["en"]}
    korean = {**shared_messages["ko"], **own_messages["ko"]}

    # HTML 키: en = 마크업 원문 (비어 있거나 한글이면 기본 언어가 영문이 아님)
    for key, english_texts in sorted(parser.english_by_key.items()):
        if any(not text for text in english_texts):
            problems.append(f"[{label}] data-i18n '{key}' 의 HTML 원문(en)이 비어 있습니다")
        if any(HANGUL_RE.search(text) for text in english_texts):
            problems.append(f"[{label}] data-i18n '{key}' 의 HTML 원문이 한글입니다 (원문은 영문, 한글은 ko 사전)")
        if key not in korean:
            problems.append(f"[{label}] ko 사전에 키가 없습니다: {key}")
    # 코드 키: en·ko 사전 둘 다
    for key in sorted(code_keys):
        if key not in english:
            problems.append(f"[{label}] en 사전에 키가 없습니다: {key}")
        if key not in korean:
            problems.append(f"[{label}] ko 사전에 키가 없습니다: {key}")
    # 사전 짝: en 키는 ko 에도
    for key in sorted(set(own_messages["en"]) - set(korean)):
        problems.append(f"[{label}] en 에만 있는 키: {key}")
    # 안 쓰는 키 (동적 키 조립 금지 — 검증 불가)
    used_keys = html_keys | code_keys
    shared_usage.update(used_keys)
    for key in sorted((set(own_messages["en"]) | set(own_messages["ko"])) - used_keys):
        problems.append(f"[{label}] 사용하지 않는 사전 키: {key}")
    # 번역 대상 밖 한글 (주석·버전 이력 제외)
    for text in parser.stray_hangul[:10]:
        problems.append(f"[{label}] 번역되지 않은 한글: {text}")
    if len(parser.stray_hangul) > 10:
        problems.append(f"[{label}] 번역되지 않은 한글 외 {len(parser.stray_hangul) - 10}건")
    return problems


def check() -> list[str]:
    problems: list[str] = []
    if not I18N_ENGINE.exists():
        return [f"[i18n] {I18N_ENGINE.name} 이 없습니다"]
    shared_messages = parse_dictionaries(I18N_ENGINE, problems)
    for key in sorted(set(shared_messages["en"]) ^ set(shared_messages["ko"])):
        problems.append(f"[i18n] wizard-i18n.js 공통 사전 en·ko 짝이 맞지 않습니다: {key}")

    shared_usage = set(TRANSLATE_CALL_RE.findall(read_text(SHARED_COMMON_JS)))
    for label, html_path, prefix, engine_src, uses_common in I18N_PAGES:
        problems.extend(check_page(label, html_path, prefix, engine_src, uses_common, shared_messages, shared_usage))
    for key in sorted(set(shared_messages["en"]) - shared_usage):
        problems.append(f"[i18n] 공통 사전에 쓰지 않는 키: {key}")
    return problems


def main() -> int:
    problems = check()
    for problem in problems:
        print(f"  - {problem}")
    print(f"i18n: {len(problems)} problem(s)" if problems else "i18n: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
