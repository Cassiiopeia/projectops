"""파일을 넘는 냄새 (scan 전용): 긴 함수, 공통 지점 우회·공통화 후보, 같은 값 상수 중복

모두 후보다. 우회는 "공통 지점이 이미 있다"는 근거(wrappers)를 함께 내고, 공통 지점이 없으면 세 번째 원칙 후보로 낸다.
"""
from __future__ import annotations

import re

from .naming_smells import without_string_literals

# 긴 함수 (단계가 여러 개 섞였다는 신호 — conventions §3.3·§8 첫 줄)
LONG_FUNCTION_LINES = 60
CONTROL_KEYWORDS = {"if", "for", "while", "switch", "catch", "synchronized", "return", "new", "else", "try", "do",
                    "when", "foreach", "using", "class", "interface", "enum", "record", "object", "with", "super", "this"}
SLASH_FUNCTION_START_PATTERNS = (
    re.compile(r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:[\w<>\[\],.?]+\s+)*([A-Za-z_$][\w$]*)\s*\([^;]*\)\s*"
               r"(?:async\*?\s*|throws\s+[\w., ]+\s*|:\s*[\w<>\[\]|?,. ]+\s*)?\{\s*$"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*[^=]+)?=>\s*\{\s*$"),
)
PYTHON_FUNCTION_START_PATTERN = re.compile(r"^([ \t]*)(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")

# 공통 지점 후보 폴더 (여기서 원본 API를 감싸면 래퍼로 본다)
# lib 는 src/lib 일 때만 (Flutter lib/ 는 앱 전체), client 는 모노레포 폴더 이름이라 넣지 않는다
COMMON_DIRECTORY_NAMES = {"design", "design_system", "common", "core", "shared", "ui", "network", "http",
                          "apis", "api", "clients", "infrastructure", "infra", "utils", "support"}
# 원본 API 직접 호출 (스택 문서 "자주 나오는 AI 냄새"의 사실판) — (언어 집합, 이름, 패턴)
DIRECT_CALL_PATTERNS = (
    ({"dart"}, "CircularProgressIndicator(", re.compile(r"\bCircularProgressIndicator\(")),
    ({"dart"}, "CupertinoActivityIndicator(", re.compile(r"\bCupertinoActivityIndicator\(")),
    ({"dart"}, "showModalBottomSheet(", re.compile(r"\bshowModalBottomSheet\s*[(<]")),
    ({"dart"}, "showDialog(", re.compile(r"\bshow(?:Cupertino)?Dialog\s*[(<]")),
    ({"dart"}, "AlertDialog(", re.compile(r"\b(?:Cupertino)?AlertDialog\(")),
    ({"dart"}, "SnackBar(", re.compile(r"\bSnackBar\(")),
    ({"dart"}, "ListTile(", re.compile(r"\bListTile\(")),
    ({"dart"}, "Image.asset(", re.compile(r"\b(?:Image|SvgPicture)\.asset\(")),
    ({"javascript", "typescript"}, "fetch(", re.compile(r"(?<![\w.])fetch\(")),
    ({"javascript", "typescript"}, "axios.<method>(", re.compile(r"\baxios\.(?:get|post|put|patch|delete|request)\(")),
    ({"javascript", "typescript"}, "sessionStorage/localStorage", re.compile(r"\b(?:session|local)Storage\.(?:get|set|remove)Item\(")),
    ({"javascript", "typescript"}, "window.confirm/alert(", re.compile(r"(?<![\w.])(?:window\.)?(?:confirm|alert)\(")),
    ({"java", "kotlin"}, "new RestTemplate/WebClient", re.compile(r"\bnew\s+RestTemplate\(|\bWebClient\.(?:create|builder)\(")),
    ({"java", "kotlin"}, "new ObjectMapper(", re.compile(r"\bnew\s+ObjectMapper\(|\bObjectMapper\(\)")),
    ({"python"}, "direct requests/httpx call", re.compile(r"\b(?:requests|httpx)\.(?:get|post|put|patch|delete|request)\(")),
)
# 공통 지점이 없을 때 이 파일 수 이상이면 공통화 후보 (세 번째 원칙 — conventions §1)
RULE_OF_THREE_FILES = 3

# 이름 있는 상수 정의 (값이 문자열·숫자 리터럴인 것만)
CONSTANT_DEFINITION_PATTERNS = {
    "java": re.compile(r"\bstatic\s+final\s+[\w<>]+\s+([A-Z][A-Z0-9_]+)\s*=\s*(\"[^\"]{3,}\"|-?\d[\d_.]*[LlFfDd]?)\s*;"),
    "kotlin": re.compile(r"\bconst\s+val\s+([A-Z][A-Z0-9_]+)\s*(?::\s*\w+)?\s*=\s*(\"[^\"]{3,}\"|-?\d[\d_.]*)"),
    "dart": re.compile(r"\bconst\s+(?:[\w<>]+\s+)?([a-zA-Z_]\w*)\s*=\s*('[^']{3,}'|\"[^\"]{3,}\"|-?\d[\d_.]*)\s*;"),
    "python": re.compile(r"^([A-Z][A-Z0-9_]+)\s*(?::\s*\w+)?\s*=\s*('[^']{3,}'|\"[^\"]{3,}\"|-?\d[\d_.]*)\s*(?:#.*)?$"),
    "javascript": re.compile(r"\bconst\s+([A-Z][A-Z0-9_]+)\s*(?::\s*\w+)?\s*=\s*('[^']{3,}'|\"[^\"]{3,}\"|`[^`$]{3,}`|-?\d[\d_.]*)\s*;?"),
}
CONSTANT_DEFINITION_PATTERNS["typescript"] = CONSTANT_DEFINITION_PATTERNS["javascript"]


def long_functions(text: str, language: str) -> list[dict]:
    """60줄 넘는 함수·메서드 [{name, line, lines}] (중괄호 짝 / 파이썬 들여쓰기 기준 근사)"""
    lines = text.splitlines()
    if language == "python":
        return _long_python_functions(lines)
    found = []
    for index, raw in enumerate(lines):
        code = without_string_literals(raw.split("//", 1)[0])
        name = next((m.group(1) for p in SLASH_FUNCTION_START_PATTERNS for m in [p.match(code)] if m), None)
        if not name or name in CONTROL_KEYWORDS:
            continue
        depth, end = 0, index
        for end in range(index, len(lines)):
            body_code = without_string_literals(lines[end].split("//", 1)[0])
            depth += body_code.count("{") - body_code.count("}")
            if depth <= 0 and end > index:
                break
        length = end - index + 1
        if length > LONG_FUNCTION_LINES:
            found.append({"name": name, "line": index + 1, "lines": length})
    return found


def _long_python_functions(lines: list[str]) -> list[dict]:
    found = []
    for index, raw in enumerate(lines):
        match = PYTHON_FUNCTION_START_PATTERN.match(raw)
        if not match:
            continue
        indent = len(match.group(1).expandtabs())
        end = index
        for end in range(index + 1, len(lines)):
            line = lines[end]
            if line.strip() and len(line) - len(line.lstrip()) <= indent and not line.lstrip().startswith((")", "]")):
                end -= 1
                break
        length = end - index + 1
        if length > LONG_FUNCTION_LINES:
            found.append({"name": match.group(2), "line": index + 1, "lines": length})
    return found


def direct_call_findings(files: list, limit: int) -> tuple[list, list]:
    """(우회, 공통화 후보) — files: [(상대경로, 언어, 코드 줄 [(번호, 줄)])]

    우회: 공통 폴더 안에 같은 원본 호출이 있는데(래퍼 후보) 그 밖에서도 직접 부름
    공통화 후보: 래퍼가 없고 3개 파일 이상에서 직접 부름
    """
    bypassed, unwrapped = [], []
    for languages, label, pattern in DIRECT_CALL_PATTERNS:
        usages_by_file = {}
        for relative, language, code_lines in files:
            if language not in languages:
                continue
            hits = [number for number, line in code_lines if pattern.search(without_string_literals(line))]
            if hits:
                usages_by_file[relative] = hits
        if not usages_by_file:
            continue
        wrappers = sorted(p for p in usages_by_file if _is_common_location(p))
        outside = {p: hits for p, hits in usages_by_file.items() if p not in wrappers}
        usage_list = [{"path": p, "line": hits[0], "count": len(hits)} for p, hits in sorted(outside.items())]
        if wrappers and outside:
            bypassed.append({"call": label, "wrappers": wrappers[:5], "files": len(outside),
                             "usages": usage_list[:limit]})
        elif not wrappers and len(outside) >= RULE_OF_THREE_FILES:
            unwrapped.append({"call": label, "files": len(outside), "usages": usage_list[:limit]})
    bypassed.sort(key=lambda b: -b["files"])
    unwrapped.sort(key=lambda u: -u["files"])
    return bypassed, unwrapped


def duplicate_constant_findings(files: list) -> list[dict]:
    """같은 값 상수가 2개 파일 이상 (설정값·키 이름은 2곳이어도 단일 원본 — conventions §1·§5)

    문자열은 값으로, 숫자는 이름+값으로 묶는다 (0·1 같은 흔한 숫자가 이름만 달라 묶이는 것 방지)
    """
    groups = {}
    for relative, language, code_lines in files:
        pattern = CONSTANT_DEFINITION_PATTERNS.get(language)
        if not pattern:
            continue
        for number, line in code_lines:
            for match in pattern.finditer(line):
                name, value = match.group(1), match.group(2)
                key = ("value", value.strip("'\"`")) if value[0] in "'\"`" else ("name", f"{name}={value}")
                groups.setdefault(key, []).append({"path": relative, "line": number, "name": name})
    duplicates = []
    for (kind, value), definitions in groups.items():
        if len({d["path"] for d in definitions}) >= 2:
            duplicates.append({"value": value, "grouped_by": kind, "definitions": definitions[:8]})
    duplicates.sort(key=lambda d: -len(d["definitions"]))
    return duplicates


def _is_common_location(relative: str) -> bool:
    directories = relative.split("/")[:-1]
    return bool(COMMON_DIRECTORY_NAMES & set(directories)) or "src/lib" in "/".join(directories)
