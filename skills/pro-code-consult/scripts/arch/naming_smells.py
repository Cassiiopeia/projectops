"""Naming smell detection (shared by scan and diff): boolean names and functions, abbreviations, meaningless names, file name ↔ type name

No verdicts — only candidates. Places where renaming breaks a contract (serialization, config binding, framework overrides) are
skipped or tagged contract so the agent can separate "fix now" from "needs a migration plan".
"""
from __future__ import annotations

import re
from pathlib import Path

from .source_files import split_identifier_words

BOOLEAN_PREFIX_PATTERN = re.compile(r"^_*(?:is|has|can|should)(?:[A-Z_0-9]|$)")
# Function names also accept standard-library question forms (exists, contains, equals, matches — including Spring Data existsBy)
QUESTION_FUNCTION_PATTERN = re.compile(r"^_*(?:is|has|can|should|exists|contains|equals|matches)(?:[A-Z_0-9]|$)")
# React hooks and Dart function types are not function names
NOT_A_FUNCTION_NAME_PATTERN = re.compile(r"^(?:use[A-Z]\w*|Function)$")
OVERRIDE_MARKER_PATTERN = re.compile(r"@(?:override|Override)\b|\boverride\s+fun\b")

BOOLEAN_DECLARATION_PATTERNS = {
    "dart": [re.compile(r"\bbool\??\s+(?:get\s+)?(?!operator\b|Function\b)([A-Za-z_]\w*)\s*(?:[=;,){]|=>)")],
    "java": [re.compile(r"\b(?:boolean|Boolean)\s+([A-Za-z_]\w*)\s*[=;,)]")],
    "kotlin": [re.compile(r"\b(?:val|var)\s+([A-Za-z_]\w*)\s*:\s*Boolean\b")],
    "python": [re.compile(r"\b([A-Za-z_]\w*)\s*:\s*bool\b")],
    "javascript": [re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:true|false)\b"),
                   re.compile(r"\bconst\s*\[\s*([A-Za-z_$][\w$]*)\s*,\s*set\w*\s*\]\s*=\s*useState(?:<boolean>)?\(\s*(?:true|false)\s*\)")],
    "typescript": [re.compile(r"\b([A-Za-z_$][\w$]*)\??\s*:\s*boolean\b"),
                   re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:true|false)\b"),
                   re.compile(r"\bconst\s*\[\s*([A-Za-z_$][\w$]*)\s*,\s*set\w*\s*\]\s*=\s*useState(?:<boolean>)?\(\s*(?:true|false)\s*\)")],
}
BOOLEAN_FUNCTION_PATTERNS = {
    "dart": [re.compile(r"\bbool\s+(?!operator\b|Function\b)([A-Za-z_]\w*)\s*\(")],
    "java": [re.compile(r"\b(?:boolean|Boolean)\s+([A-Za-z_]\w*)\s*\(")],
    "kotlin": [re.compile(r"\bfun\s+([A-Za-z_]\w*)\s*\([^)]*\)\s*:\s*Boolean\b")],
    "python": [re.compile(r"\bdef\s+([A-Za-z_]\w*)\s*\([^)]*\)\s*->\s*bool\b")],
    "typescript": [re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*:\s*boolean\b")],
}

# Contract fields (renaming breaks JSON, config keys, DB columns): file path or content markers
CONTRACT_PATH_PATTERN = re.compile(r"(?:^|/)(?:dto|dtos|request|requests|response|responses|properties|entity|entities|models?)(?:/|$)|"
                                   r"(?:Request|Response|Dto|DTO|Properties|Entity)\.\w+$|_(?:request|response|dto|model)\.\w+$")
CONTRACT_ANNOTATION_PATTERN = re.compile(r"@(?:ConfigurationProperties|JsonProperty|JsonKey|Entity|Table|Column|freezed|JsonSerializable|Serializable)\b")

# Abbreviations (industry-standard id, url, api, json, http, sql, ui, dto, jwt, uuid, db allowed — conventions §2.2)
# info and util are not abbreviations but "meaningless when standalone" (compounds like memberInfo, JwtUtil are allowed)
ABBREVIATION_WORDS = {
    "svc", "repo", "repos", "mgr", "btn", "idx", "tmp", "res", "resp", "req", "cnt", "cur", "curr",
    "prev", "pre", "msg", "msgs", "str", "num", "val", "vals", "cfg", "conf", "img", "imgs", "pwd",
    "usr", "addr", "lbl", "txt", "calc", "cb", "evt", "elem", "el", "obj", "arr", "len", "sz", "err",
    "desc", "dt", "proc", "pos", "temp", "buf",
}
MEANINGLESS_NAMES = {"data", "info", "item", "value", "temp", "tmp", "result", "manager", "helper", "util", "utils", "obj", "thing", "stuff"}
TYPE_DECLARATION_PATTERN = re.compile(r"\b(?:class|enum|interface|mixin|record|typedef)\s+([A-Za-z_$][\w$]*)")
FUNCTION_DECLARATION_PATTERN = re.compile(r"\b(?:def|function|fun)\s+([A-Za-z_$][\w$]*)")
# Keyword declarations: skip the type if present and capture the variable name (final JwtUtil jwtUtil > jwtUtil)
KEYWORD_VARIABLE_PATTERN = re.compile(
    r"\b(?:final|late|const|var|val|let)\s+(?:[\w$.]+(?:<[^=;()]*>)?\??(?:\[\])*\s+)?([A-Za-z_$][\w$]*)\s*(?=[=;:,)]|\bin\b|$)")
# Typed declarations (Java/Dart: Member curMember = ..., private String value;)
TYPED_VARIABLE_PATTERN = re.compile(
    r"(?:^|[{;])\s*(?:(?:private|public|protected|static|final|transient|volatile|late|required)\s+)*"
    r"(?:[A-Z][\w$]*(?:<[^=;()]*>)?(?:\[\])?\??|int|long|double|float|char|byte|short|bool|num|dynamic)\s+([a-z_$][\w$]*)\s*[=;]")
TYPED_VARIABLE_LANGUAGES = {"java", "dart"}
IGNORED_DECLARED_NAMES = {"i", "j", "k", "e", "_", "x", "y", "z", "it", "self", "cls", "args", "kwargs", "main", "n", "t"}
STRING_LITERAL_PATTERN = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`")

# Files skipped by the file name ≠ type name check (barrel and convention files)
BUNDLE_FILE_SUFFIX_PATTERN = re.compile(r"_(?:parts|providers|extensions?|utils?|constants|routes|types|widgets)$")


def without_string_literals(line: str) -> str:
    return STRING_LITERAL_PATTERN.sub('""', line)


def is_override_context(previous_lines: str) -> bool:
    return bool(OVERRIDE_MARKER_PATTERN.search(previous_lines))


def contract_reason(relative_path: str, text: str) -> str | None:
    """Why this file's field names are an external contract (None if not)"""
    annotation = CONTRACT_ANNOTATION_PATTERN.search(text)
    if annotation:
        return annotation.group(0)
    if CONTRACT_PATH_PATTERN.search(relative_path):
        return "dto/config/model path"
    return None


def boolean_names_in_line(line: str, language: str) -> list[str]:
    """Boolean names without an is/has/can/should prefix (string contents ignored)"""
    code = without_string_literals(line)
    names = []
    for pattern in BOOLEAN_DECLARATION_PATTERNS.get(language, []):
        for match in pattern.finditer(code):
            name = match.group(1)
            if name and not BOOLEAN_PREFIX_PATTERN.match(name) and name not in IGNORED_DECLARED_NAMES:
                names.append(name)
    return names


def boolean_function_names_in_line(line: str, language: str) -> list[str]:
    """Boolean-returning function names not phrased as questions"""
    code = without_string_literals(line)
    return [m.group(1) for p in BOOLEAN_FUNCTION_PATTERNS.get(language, []) for m in p.finditer(code)
            if not QUESTION_FUNCTION_PATTERN.match(m.group(1)) and not NOT_A_FUNCTION_NAME_PATTERN.match(m.group(1))]


def naming_findings_in_line(line: str, language: str = "") -> list[tuple[str, str, str]]:
    """Abbreviations and meaningless names among declared names: [(kind, name, matched word)]

    Type names are checked for abbreviations only (class Item is a domain name). Single-letter locals are reported as meaningless.
    """
    code = without_string_literals(line)
    declared = [(m.group(1), "type") for m in TYPE_DECLARATION_PATTERN.finditer(code)]
    declared += [(m.group(1), "function") for m in FUNCTION_DECLARATION_PATTERN.finditer(code)]
    declared += [(m.group(1), "variable") for m in KEYWORD_VARIABLE_PATTERN.finditer(code)]
    if language in TYPED_VARIABLE_LANGUAGES:
        declared += [(m.group(1), "variable") for m in TYPED_VARIABLE_PATTERN.finditer(code)]
    findings, seen = [], set()
    for name, kind in declared:
        # Language special methods (__str__, etc.) cannot choose their names
        if name in seen or name in IGNORED_DECLARED_NAMES or re.fullmatch(r"__\w+__", name):
            continue
        seen.add(name)
        if len(name) == 1:
            if kind == "variable":
                findings.append(("meaningless_name", name, name))
            continue
        if kind != "type" and name.lower().strip("_") in MEANINGLESS_NAMES:
            # Variable name = type name (Item item) is a domain name, so normal
            if not re.search(rf"\b{re.escape(name.strip('_')[:1].upper() + name.strip('_')[1:])}\b", code):
                findings.append(("meaningless_name", name, name.lower()))
            continue
        word = next((w for w in split_identifier_words(name) if w in ABBREVIATION_WORDS), None)
        if word:
            findings.append(("abbreviation", name, word))
    return findings


def file_type_name_mismatch(relative_path: str, language: str, text: str) -> str | None:
    """If file name ≠ main type name, the file's first public type name (Dart and JSX/TSX components only, case-insensitive)"""
    stem = Path(relative_path).stem
    if language == "dart":
        if stem in {"main", "app", "app_router"} or "_test" in stem or BUNDLE_FILE_SUFFIX_PATTERN.search(stem):
            return None
        expected = "".join(word.capitalize() for word in stem.split("_"))
        types = re.findall(
            r"^(?:(?:abstract|sealed|final|base|interface)\s+)*(?:class|enum|mixin|extension\s+type)\s+([A-Z]\w*)",
            text, re.MULTILINE)
        # Files owned by a top-level function (show_notice_popup.dart > showNoticePopup)
        function_name = expected[:1].lower() + expected[1:]
        if re.search(rf"^[\w<>?,\s]*\b{re.escape(function_name)}\s*[(<]", text, re.MULTILINE):
            return None
        if types and expected.lower() not in {t.lower() for t in types}:
            return types[0]
    elif relative_path.endswith((".tsx", ".jsx")) and stem[:1].isupper() and stem != "index":
        exported = re.findall(r"\bexport\s+(?:default\s+)?(?:function|class|const)\s+([A-Z]\w*)", text)
        if exported and stem.lower() not in {e.lower() for e in exported}:
            return exported[0]
    return None
