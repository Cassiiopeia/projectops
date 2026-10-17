"""이름 냄새 탐지 (scan·diff 공용): boolean 이름·함수, 약어, 뜻 없는 이름, 파일명 ↔ 타입명

판정은 하지 않는다 — 후보만 낸다. 바꾸면 계약이 깨지는 자리(직렬화·설정 바인딩·프레임워크 override)는
빼거나 contract 태그를 붙여 에이전트가 "고칠 것"과 "이관 계획이 필요한 것"을 나눌 수 있게 한다.
"""
from __future__ import annotations

import re
from pathlib import Path

from .source_files import split_identifier_words

BOOLEAN_PREFIX_PATTERN = re.compile(r"^_*(?:is|has|can|should)(?:[A-Z_0-9]|$)")
# 함수 이름은 표준 라이브러리 질문형도 인정 (exists·contains·equals·matches — Spring Data existsBy 포함)
QUESTION_FUNCTION_PATTERN = re.compile(r"^_*(?:is|has|can|should|exists|contains|equals|matches)(?:[A-Z_0-9]|$)")
# React 훅·Dart 함수 타입은 함수 이름이 아님
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

# 계약 필드 (이름을 바꾸면 JSON·설정 키·DB 컬럼이 깨진다): 파일 경로 또는 본문 표식
CONTRACT_PATH_PATTERN = re.compile(r"(?:^|/)(?:dto|dtos|request|requests|response|responses|properties|entity|entities|models?)(?:/|$)|"
                                   r"(?:Request|Response|Dto|DTO|Properties|Entity)\.\w+$|_(?:request|response|dto|model)\.\w+$")
CONTRACT_ANNOTATION_PATTERN = re.compile(r"@(?:ConfigurationProperties|JsonProperty|JsonKey|Entity|Table|Column|freezed|JsonSerializable|Serializable)\b")

# 약어 (업계 표준 id·url·api·json·http·sql·ui·dto·jwt·uuid·db 는 허용 — conventions §2.2)
# info·util 은 약어가 아니라 "단독이면 뜻 없는 이름" (memberInfo·JwtUtil 같은 합성어는 허용)
ABBREVIATION_WORDS = {
    "svc", "repo", "repos", "mgr", "btn", "idx", "tmp", "res", "resp", "req", "cnt", "cur", "curr",
    "prev", "pre", "msg", "msgs", "str", "num", "val", "vals", "cfg", "conf", "img", "imgs", "pwd",
    "usr", "addr", "lbl", "txt", "calc", "cb", "evt", "elem", "el", "obj", "arr", "len", "sz", "err",
    "desc", "dt", "proc", "pos", "temp", "buf",
}
MEANINGLESS_NAMES = {"data", "info", "item", "value", "temp", "tmp", "result", "manager", "helper", "util", "utils", "obj", "thing", "stuff"}
TYPE_DECLARATION_PATTERN = re.compile(r"\b(?:class|enum|interface|mixin|record|typedef)\s+([A-Za-z_$][\w$]*)")
FUNCTION_DECLARATION_PATTERN = re.compile(r"\b(?:def|function|fun)\s+([A-Za-z_$][\w$]*)")
# 키워드 선언: 타입이 있으면 건너뛰고 변수 이름을 잡는다 (final JwtUtil jwtUtil > jwtUtil)
KEYWORD_VARIABLE_PATTERN = re.compile(
    r"\b(?:final|late|const|var|val|let)\s+(?:[\w$.]+(?:<[^=;()]*>)?\??(?:\[\])*\s+)?([A-Za-z_$][\w$]*)\s*(?=[=;:,)]|\bin\b|$)")
# 타입 선언 (Java·Dart: Member curMember = ..., private String value;)
TYPED_VARIABLE_PATTERN = re.compile(
    r"(?:^|[{;])\s*(?:(?:private|public|protected|static|final|transient|volatile|late|required)\s+)*"
    r"(?:[A-Z][\w$]*(?:<[^=;()]*>)?(?:\[\])?\??|int|long|double|float|char|byte|short|bool|num|dynamic)\s+([a-z_$][\w$]*)\s*[=;]")
TYPED_VARIABLE_LANGUAGES = {"java", "dart"}
IGNORED_DECLARED_NAMES = {"i", "j", "k", "e", "_", "x", "y", "z", "it", "self", "cls", "args", "kwargs", "main", "n", "t"}
STRING_LITERAL_PATTERN = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`")

# 파일명 ≠ 타입명 검사에서 뺄 파일 (묶음·관례 파일)
BUNDLE_FILE_SUFFIX_PATTERN = re.compile(r"_(?:parts|providers|extensions?|utils?|constants|routes|types|widgets)$")


def without_string_literals(line: str) -> str:
    return STRING_LITERAL_PATTERN.sub('""', line)


def is_override_context(previous_lines: str) -> bool:
    return bool(OVERRIDE_MARKER_PATTERN.search(previous_lines))


def contract_reason(relative_path: str, text: str) -> str | None:
    """이 파일의 필드 이름이 외부 계약인 이유 (없으면 None)"""
    annotation = CONTRACT_ANNOTATION_PATTERN.search(text)
    if annotation:
        return annotation.group(0)
    if CONTRACT_PATH_PATTERN.search(relative_path):
        return "dto·설정·모델 경로"
    return None


def boolean_names_in_line(line: str, language: str) -> list[str]:
    """접두사(is/has/can/should) 없는 boolean 이름 (문자열 안은 보지 않음)"""
    code = without_string_literals(line)
    names = []
    for pattern in BOOLEAN_DECLARATION_PATTERNS.get(language, []):
        for match in pattern.finditer(code):
            name = match.group(1)
            if name and not BOOLEAN_PREFIX_PATTERN.match(name) and name not in IGNORED_DECLARED_NAMES:
                names.append(name)
    return names


def boolean_function_names_in_line(line: str, language: str) -> list[str]:
    """질문형 아닌 boolean 반환 함수 이름"""
    code = without_string_literals(line)
    return [m.group(1) for p in BOOLEAN_FUNCTION_PATTERNS.get(language, []) for m in p.finditer(code)
            if not QUESTION_FUNCTION_PATTERN.match(m.group(1)) and not NOT_A_FUNCTION_NAME_PATTERN.match(m.group(1))]


def naming_findings_in_line(line: str, language: str = "") -> list[tuple[str, str, str]]:
    """선언된 이름의 약어·뜻 없는 이름: [(종류, 이름, 걸린 단어)]

    타입 이름은 약어만 본다 (class Item 은 도메인 이름). 한 글자 지역 변수는 뜻 없는 이름으로 낸다.
    """
    code = without_string_literals(line)
    declared = [(m.group(1), "type") for m in TYPE_DECLARATION_PATTERN.finditer(code)]
    declared += [(m.group(1), "function") for m in FUNCTION_DECLARATION_PATTERN.finditer(code)]
    declared += [(m.group(1), "variable") for m in KEYWORD_VARIABLE_PATTERN.finditer(code)]
    if language in TYPED_VARIABLE_LANGUAGES:
        declared += [(m.group(1), "variable") for m in TYPED_VARIABLE_PATTERN.finditer(code)]
    findings, seen = [], set()
    for name, kind in declared:
        # 언어 특수 메서드(__str__ 등)는 이름을 고를 수 없다
        if name in seen or name in IGNORED_DECLARED_NAMES or re.fullmatch(r"__\w+__", name):
            continue
        seen.add(name)
        if len(name) == 1:
            if kind == "variable":
                findings.append(("meaningless_name", name, name))
            continue
        if kind != "type" and name.lower().strip("_") in MEANINGLESS_NAMES:
            # 변수 이름 = 타입 이름 (Item item) 은 도메인 이름이라 정상
            if not re.search(rf"\b{re.escape(name.strip('_')[:1].upper() + name.strip('_')[1:])}\b", code):
                findings.append(("meaningless_name", name, name.lower()))
            continue
        word = next((w for w in split_identifier_words(name) if w in ABBREVIATION_WORDS), None)
        if word:
            findings.append(("abbreviation", name, word))
    return findings


def file_type_name_mismatch(relative_path: str, language: str, text: str) -> str | None:
    """파일명 ≠ 주된 타입명이면 그 파일의 첫 공개 타입 이름 (Dart·JSX/TSX 컴포넌트만, 대소문자 무시)"""
    stem = Path(relative_path).stem
    if language == "dart":
        if stem in {"main", "app", "app_router"} or "_test" in stem or BUNDLE_FILE_SUFFIX_PATTERN.search(stem):
            return None
        expected = "".join(word.capitalize() for word in stem.split("_"))
        types = re.findall(
            r"^(?:(?:abstract|sealed|final|base|interface)\s+)*(?:class|enum|mixin|extension\s+type)\s+([A-Z]\w*)",
            text, re.MULTILINE)
        # 최상위 함수가 주인인 파일 (show_notice_popup.dart > showNoticePopup)
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
