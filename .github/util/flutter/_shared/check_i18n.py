#!/usr/bin/env python3
"""Language switch check for the HTML wizards (#769) — run together by check-consistency.py.

Targets: the 4 Flutter wizards + 2 common wizards (I18N_PAGES)
5 checks: engine load order, dictionary JSON format, missing keys (en/ko), unused keys, leftover Korean in the HTML body

2 sources of en
  - Static markup: HTML content of data-i18n elements (= the page's default English)
  - Dynamic text : en in the registerWizardMessages dictionary
ko all lives in the dictionary. So the "en dictionary" is HTML extraction ∪ dictionary en for comparison.

Run alone:
    python3 .github/util/flutter/_shared/check_i18n.py
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# Keep emoji output from crashing a cp949 console
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SHARED_DIR = Path(__file__).resolve().parent
UTIL_DIR = SHARED_DIR.parent.parent
I18N_ENGINE = SHARED_DIR / "wizard-i18n.js"
SHARED_COMMON_JS = SHARED_DIR / "wizard-common.js"

# (display name, HTML, page JS glob prefix, engine src, whether wizard-common.js is used)
I18N_PAGES = (
    ("testflight", UTIL_DIR / "flutter/testflight-wizard/testflight-wizard.html", "testflight-wizard", "../_shared/wizard-i18n.js", True),
    ("playstore", UTIL_DIR / "flutter/playstore-wizard/playstore-wizard.html", "playstore-wizard", "../_shared/wizard-i18n.js", True),
    ("firebase", UTIL_DIR / "flutter/firebase-wizard/firebase-wizard.html", "firebase-wizard", "../_shared/wizard-i18n.js", True),
    ("oauth", UTIL_DIR / "flutter/oauth-wizard/oauth-wizard.html", "oauth-wizard", "../_shared/wizard-i18n.js", True),
    ("projects-sync", UTIL_DIR / "common/projects-sync-wizard/projects-sync-wizard.html", "projects-sync-wizard", "../../flutter/_shared/wizard-i18n.js", False),
    ("secrets-converter", UTIL_DIR / "common/github-secrets-converter/secrets-converter.html", "secrets-converter", "../../flutter/_shared/wizard-i18n.js", False),
)

HANGUL_RE = re.compile(r"[가-힣]")
KEY_ATTRIBUTES = ("data-i18n", "data-i18n-placeholder", "data-i18n-title")
# Keyed attribute > the actual attribute that key changes
TRANSLATED_ATTRIBUTE_BY_KEY_ATTRIBUTE = {"data-i18n-placeholder": "placeholder", "data-i18n-title": "title"}
TRANSLATE_CALL_RE = re.compile(r"""\btranslate\(\s*['"`]([A-Za-z0-9_.-]+)['"`]""")
REGISTER_CALL_RE = re.compile(r"registerWizardMessages\(\s*(?=\{)")
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# HTML areas allowed to contain Korean: comments, <style> (CSS comments), changelog (versionJson — past records stay as written)
LANGUAGE_NEUTRAL_SCRIPT_IDS = {"versionJson"}


class TranslatableMarkupParser(HTMLParser):
    """Collect the source text (en) and attribute source text of data-i18n elements + Korean text outside translation targets"""

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
            # The toggle button label (한국어/English) is filled by the engine
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
        # Close up to the innermost open element with the same tag (tolerates badly closed markup)
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
    """registerWizardMessages({...}) block > {"en": {...}, "ko": {...}} (JSON format only)"""
    merged: dict[str, dict[str, str]] = {"en": {}, "ko": {}}
    source = read_text(path)
    decoder = json.JSONDecoder()
    for match in REGISTER_CALL_RE.finditer(source):
        try:
            messages, _ = decoder.raw_decode(source, match.end())
        except json.JSONDecodeError as error:
            problems.append(f"[i18n] {path.name}: dictionary is not in JSON format ({error})")
            continue
        for language in ("en", "ko"):
            merged[language].update(messages.get(language, {}))
    return merged


def page_js_files(html_path: Path, prefix: str) -> list[Path]:
    return sorted(html_path.parent.glob(f"{prefix}*.js"))


def check_load_order(label: str, html: str, engine_src: str, prefix: str, uses_common: bool) -> list[str]:
    """Engine > (wizard-common.js) > dictionary > wizard JS order"""
    problems = []
    engine_index = html.find(f'src="{engine_src}"')
    dictionary_index = html.find(f'src="{prefix}-i18n.js"')
    main_index = html.find(f'src="{prefix}.js"')
    if engine_index == -1:
        return [f"[{label}] does not load the language engine: {engine_src}"]
    if dictionary_index == -1:
        problems.append(f"[{label}] does not load the dictionary {prefix}-i18n.js")
    elif main_index != -1 and dictionary_index > main_index:
        problems.append(f"[{label}] dictionary {prefix}-i18n.js loads after {prefix}.js")
    if uses_common:
        common_index = html.find('src="../_shared/wizard-common.js"')
        if common_index != -1 and engine_index > common_index:
            problems.append(f"[{label}] wizard-i18n.js loads after wizard-common.js")
    if "data-lang-toggle" not in html:
        problems.append(f"[{label}] no language toggle button (data-lang-toggle)")
    return problems


def check_page(label, html_path, prefix, engine_src, uses_common, shared_messages, shared_usage) -> list[str]:
    """One page: load order > key comparison (en/ko) > unused keys > leftover Korean"""
    html = read_text(html_path)
    if not html:
        return [f"[{label}] {html_path.name} is missing"]
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

    # HTML keys: en = markup source (empty or Korean means the default language is not English)
    for key, english_texts in sorted(parser.english_by_key.items()):
        if any(not text for text in english_texts):
            problems.append(f"[{label}] HTML source (en) of data-i18n '{key}' is empty")
        if any(HANGUL_RE.search(text) for text in english_texts):
            problems.append(f"[{label}] HTML source of data-i18n '{key}' is Korean (the source is English; Korean goes in the ko dictionary)")
        if key not in korean:
            problems.append(f"[{label}] key missing from the ko dictionary: {key}")
    # Code keys: both en and ko dictionaries
    for key in sorted(code_keys):
        if key not in english:
            problems.append(f"[{label}] key missing from the en dictionary: {key}")
        if key not in korean:
            problems.append(f"[{label}] key missing from the ko dictionary: {key}")
    # Dictionary pairs: en keys must be in ko too
    for key in sorted(set(own_messages["en"]) - set(korean)):
        problems.append(f"[{label}] key only in en: {key}")
    # Unused keys (no dynamically assembled keys — they cannot be checked)
    used_keys = html_keys | code_keys
    shared_usage.update(used_keys)
    for key in sorted((set(own_messages["en"]) | set(own_messages["ko"])) - used_keys):
        problems.append(f"[{label}] unused dictionary key: {key}")
    # Korean outside translation targets (comments and changelog excluded)
    for text in parser.stray_hangul[:10]:
        problems.append(f"[{label}] untranslated Korean: {text}")
    if len(parser.stray_hangul) > 10:
        problems.append(f"[{label}] untranslated Korean and {len(parser.stray_hangul) - 10} more")
    return problems


def check() -> list[str]:
    problems: list[str] = []
    if not I18N_ENGINE.exists():
        return [f"[i18n] {I18N_ENGINE.name} is missing"]
    shared_messages = parse_dictionaries(I18N_ENGINE, problems)
    for key in sorted(set(shared_messages["en"]) ^ set(shared_messages["ko"])):
        problems.append(f"[i18n] wizard-i18n.js shared dictionary en/ko pairs do not match: {key}")

    shared_usage = set(TRANSLATE_CALL_RE.findall(read_text(SHARED_COMMON_JS)))
    for label, html_path, prefix, engine_src, uses_common in I18N_PAGES:
        problems.extend(check_page(label, html_path, prefix, engine_src, uses_common, shared_messages, shared_usage))
    for key in sorted(set(shared_messages["en"]) - shared_usage):
        problems.append(f"[i18n] unused key in the shared dictionary: {key}")
    return problems


def main() -> int:
    problems = check()
    for problem in problems:
        print(f"  - {problem}")
    print(f"i18n: {len(problems)} problem(s)" if problems else "i18n: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
