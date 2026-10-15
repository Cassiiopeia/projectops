"""줄·파일 단위 냄새 탐지 (scan·diff 공용): 주석 문구, boolean 이름, 약어, 하드코딩 토큰, 삼키는 catch

판정은 하지 않는다 — 후보만 낸다. 오탐은 에이전트가 원문을 보고 거른다.
"""
from __future__ import annotations

import re
from pathlib import Path

from .source_files import split_identifier_words

# 경위 주석 (작업 이력은 커밋·이슈에 남긴다 — conventions §7.6)
HISTORY_COMMENT_PATTERN = re.compile(
    r"기존에는|예전에는|원래는|이전에는|바꿨|바꾸었|변경했|변경함|수정했|수정함|고쳤|(?<![가-힣])고침|추가했|추가함|"
    r"제거했|제거함|삭제했|삭제함|이제는|리팩터링으로|리팩토링으로|이전\s*버그|"
    r"\bpreviously\b|\bused to\b|\bno longer\b|\bnow uses?\b|\bwas changed\b|\brefactored\b|"
    r"\bchanged from\b|\bfixed (?:a |the )?bug\b|\bold (?:code|logic|version|behavior)\b",
    re.IGNORECASE,
)
# 장식 배너 (// ====, # ----)
BANNER_COMMENT_PATTERN = re.compile(r"[=\-*#~]{4,}")
# 문장체 끝맺음 (명사형·짧은 구로 끝낸다 — conventions §7)
PROSE_ENDING_PATTERN = re.compile(
    r"(?:합니다|입니다|됩니다|있습니다|없습니다|습니다|하기\s*위해|하기\s*위함|위한\s*것)\s*[.)]?\s*(?:\*/)?\s*$"
)

# 주석 블록이 이 줄 수 이상이면 "긴 블록" (클래스 문서 주석은 2줄 이내 — conventions §7.1)
LONG_COMMENT_BLOCK_LINES = 5

BOOLEAN_PREFIX_PATTERN = re.compile(r"^_*(?:is|has|can|should)(?:[A-Z_0-9]|$)")
BOOLEAN_DECLARATION_PATTERNS = {
    "dart": [re.compile(r"\bbool\??\s+(?:get\s+)?(?!operator\b)([A-Za-z_]\w*)\s*(?:[=;,){]|=>)")],
    "java": [re.compile(r"\b(?:boolean|Boolean)\s+([A-Za-z_]\w*)\s*[=;,)]")],
    "kotlin": [re.compile(r"\b(?:val|var)\s+([A-Za-z_]\w*)\s*:\s*Boolean\b")],
    "python": [re.compile(r"\b([A-Za-z_]\w*)\s*:\s*bool\b")],
    "javascript": [re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:true|false)\b"),
                   re.compile(r"\bconst\s*\[\s*([A-Za-z_$][\w$]*)\s*,\s*set\w*\s*\]\s*=\s*useState(?:<boolean>)?\(\s*(?:true|false)\s*\)")],
    "typescript": [re.compile(r"\b([A-Za-z_$][\w$]*)\??\s*:\s*boolean\b"),
                   re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:true|false)\b"),
                   re.compile(r"\bconst\s*\[\s*([A-Za-z_$][\w$]*)\s*,\s*set\w*\s*\]\s*=\s*useState(?:<boolean>)?\(\s*(?:true|false)\s*\)")],
}

# boolean 반환 함수 (질문형 이름 — conventions §2.1)
BOOLEAN_FUNCTION_PATTERNS = {
    "dart": [re.compile(r"\bbool\s+(?!operator\b)([A-Za-z_]\w*)\s*\(")],
    "java": [re.compile(r"\b(?:boolean|Boolean)\s+([A-Za-z_]\w*)\s*\(")],
    "kotlin": [re.compile(r"\bfun\s+([A-Za-z_]\w*)\s*\([^)]*\)\s*:\s*Boolean\b")],
    "python": [re.compile(r"\bdef\s+([A-Za-z_]\w*)\s*\([^)]*\)\s*->\s*bool\b")],
    "typescript": [re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*:\s*boolean\b")],
}

# 약어 (업계 표준 id·url·api·json·http·sql·ui·dto·jwt·uuid·db 는 허용 — conventions §2.2)
ABBREVIATION_WORDS = {
    "svc", "repo", "repos", "mgr", "btn", "idx", "tmp", "res", "resp", "req", "cnt", "cur", "curr",
    "prev", "pre", "msg", "msgs", "str", "num", "val", "vals", "cfg", "conf", "img", "imgs", "pwd",
    "usr", "addr", "lbl", "txt", "calc", "cb", "evt", "elem", "el", "obj", "arr", "len", "sz", "err",
    "util", "utils", "info", "desc", "dt", "proc", "pos", "temp",
}
# 단독으로 쓰면 뜻이 없는 이름 (무엇의 무엇인지 붙인다)
MEANINGLESS_NAMES = {"data", "info", "item", "value", "temp", "tmp", "result", "manager", "helper", "util", "utils", "obj", "thing", "stuff"}
DECLARED_NAME_PATTERN = re.compile(
    r"\b(?:class|enum|interface|mixin|record|def|function|fun|val|var|let|const|final|late)\s+([A-Za-z_$][\w$]*)"
)
# 이 언어 키워드·관례 이름은 이름 검사 제외
IGNORED_DECLARED_NAMES = {"i", "j", "k", "e", "_", "x", "y", "it", "self", "cls", "args", "kwargs", "main"}

HARDCODED_TOKEN_PATTERNS = {
    "dart": [
        ("color_literal", re.compile(r"\bColor\(0x")),
        ("material_color", re.compile(r"\bColors\.(?!transparent\b)[a-z]\w*")),
        ("spacing_literal", re.compile(r"\bEdgeInsets\.(?:all|symmetric|only|fromLTRB)\([^)]*\d")),
        ("font_size_literal", re.compile(r"\bfontSize:\s*\d")),
        ("radius_literal", re.compile(r"\bBorderRadius\.circular\(\s*\d")),
        ("asset_path_literal", re.compile(r"\b(?:Image|SvgPicture)\.asset\(\s*['\"]")),
    ],
    "javascript": [
        ("hex_color", re.compile(r"['\"`](?:#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?|#(?=[0-9]*[a-fA-F])[0-9a-fA-F]{3})\b")),
        ("tailwind_arbitrary_value", re.compile(r"-\[(?:#[0-9a-fA-F]{3,8}|\d+(?:px|rem))\]")),
        ("inline_style", re.compile(r"\bstyle=\{\{")),
    ],
}
HARDCODED_TOKEN_PATTERNS["typescript"] = HARDCODED_TOKEN_PATTERNS["javascript"]
# 토큰 정의 자리 (여기서는 값을 직접 쓰는 것이 정상)
TOKEN_DEFINITION_PATH_PATTERN = re.compile(r"(?:^|/)(?:theme|themes|design|tokens?|styles?|colors?)(?:/|\.|_)", re.IGNORECASE)

SWALLOWED_CATCH_PATTERNS = {
    "slash": re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}"),
    "python": re.compile(r"\bexcept\b[^:\n]*:\s*(?:#[^\n]*)?\n\s*pass\b|\bexcept\b[^:\n]*:\s*pass\b"),
}


def comment_phrase_findings(content: str) -> list[str]:
    """주석 한 줄의 문제 종류 목록: history / banner / prose_ending"""
    kinds = []
    if HISTORY_COMMENT_PATTERN.search(content):
        kinds.append("history")
    body = content.lstrip("/#*! ").rstrip("*/ ")
    if BANNER_COMMENT_PATTERN.search(body) and len(re.sub(r"[=\-*#~\s]", "", body)) < len(body) // 2:
        kinds.append("banner")
    if PROSE_ENDING_PATTERN.search(content):
        kinds.append("prose_ending")
    return kinds


def boolean_names_in_line(line: str, language: str) -> list[str]:
    """접두사(is/has/can/should) 없는 boolean 이름"""
    names = []
    for pattern in BOOLEAN_DECLARATION_PATTERNS.get(language, []):
        for match in pattern.finditer(line):
            name = match.group(1)
            if name and not BOOLEAN_PREFIX_PATTERN.match(name) and name not in IGNORED_DECLARED_NAMES:
                names.append(name)
    return names


def boolean_function_names_in_line(line: str, language: str) -> list[str]:
    """질문형(is/has/can/should) 아닌 boolean 반환 함수 이름"""
    return [m.group(1) for p in BOOLEAN_FUNCTION_PATTERNS.get(language, []) for m in p.finditer(line)
            if not BOOLEAN_PREFIX_PATTERN.match(m.group(1))]


def naming_findings_in_line(line: str) -> list[tuple[str, str, str]]:
    """선언된 이름의 약어·뜻 없는 이름: [(종류, 이름, 걸린 단어)]"""
    findings = []
    for match in DECLARED_NAME_PATTERN.finditer(line):
        name = match.group(1)
        if name in IGNORED_DECLARED_NAMES or len(name) <= 1:
            continue
        words = split_identifier_words(name)
        if name.lower().strip("_") in MEANINGLESS_NAMES:
            findings.append(("meaningless_name", name, name.lower()))
            continue
        for word in words:
            if word in ABBREVIATION_WORDS:
                findings.append(("abbreviation", name, word))
                break
    return findings


def hardcoded_tokens_in_line(line: str, language: str, relative_path: str) -> list[str]:
    if TOKEN_DEFINITION_PATH_PATTERN.search(relative_path):
        return []
    return [kind for kind, pattern in HARDCODED_TOKEN_PATTERNS.get(language, []) if pattern.search(line)]


def swallowed_catch_lines(text: str, language: str) -> list[int]:
    pattern = SWALLOWED_CATCH_PATTERNS["python" if language == "python" else "slash"]
    return [text.count("\n", 0, match.start()) + 1 for match in pattern.finditer(text)]


def file_type_name_mismatch(relative_path: str, language: str, text: str) -> str | None:
    """파일명 ≠ 주된 타입명이면 그 파일의 첫 공개 타입 이름 (Dart·JSX/TSX 컴포넌트만)"""
    stem = Path(relative_path).stem
    if language == "dart":
        if stem in {"main", "app_router"} or "_test" in stem:
            return None
        expected = "".join(word.capitalize() for word in stem.split("_"))
        types = re.findall(
            r"^(?:(?:abstract|sealed|final|base|interface)\s+)*(?:class|enum|mixin|extension\s+type)\s+([A-Z]\w*)",
            text, re.MULTILINE)
        if types and expected not in types:
            return types[0]
    elif relative_path.endswith((".tsx", ".jsx")) and stem[:1].isupper() and stem != "index":
        exported = re.findall(r"\bexport\s+(?:default\s+)?(?:function|class|const)\s+([A-Z]\w*)", text)
        if exported and stem not in exported:
            return exported[0]
    return None
