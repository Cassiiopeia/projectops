"""줄·파일 단위 냄새 탐지 (scan·diff 공용): 주석 문구·블록, 하드코딩 토큰·URL, catch 처리, 린트 끄기

판정은 하지 않는다 — 후보와 판단 단서(태그)만 낸다. 오탐은 에이전트가 원문을 보고 거른다.
이름 냄새는 naming_smells, 파일을 넘는 냄새(우회·중복 상수·긴 함수)는 structure_smells.
"""
from __future__ import annotations

import re

from .naming_smells import (boolean_function_names_in_line, boolean_names_in_line,  # noqa: F401 — diff_review 호환
                            file_type_name_mismatch, naming_findings_in_line, without_string_literals)

# 경위 주석 (작업 이력은 커밋·이슈에 남긴다 — conventions §7.6)
# 명사형 끝맺음(추가함·삭제함)은 현재 동작 설명에도 쓰여(conventions §7 권장 형태) 넣지 않는다
HISTORY_COMMENT_PATTERN = re.compile(
    r"기존에는|예전에는|예전엔|원래는|이전에는|이제는|"
    r"바꿨|바꾸었|(?<!줄)바꿈(?![가-힣])|변경했|수정했|고쳤|추가했|제거했|삭제했|옮겼|걷어냈|없앴|되돌렸|뒤집었|바뀌었|통일했|통일함|"
    r"리팩터링으로|리팩토링으로|이전\s*버그|문제가\s*있었|그대로\s*옮|통합\s*후|"
    r"기존\s*\S*\s*(?:방식|메서드|로직|코드|구조|버전)|기존\s*\S+\s*(?:→|->)|에서\s*(?:\S+\s*(?:으로|로)\s*)?전환|"
    r"(?:으로|로)\s*(?:변경|통합|교체)(?:했|함|되었|됐)|"
    r"\bpreviously\b|\bused to\b|\bno longer\b|\bnow uses?\b|\bwas changed\b|\brefactored\b|"
    r"\bchanged from\b|\bfixed (?:a |the )?bug\b|\bold (?:code|logic|version|behavior)\b|\bmigrated from\b",
    re.IGNORECASE,
)
# 경위가 아닌 문장: 사용자·관리자의 동작, 가정·조건 ("관리자가 바꿨을 뿐인데", "추가했는지")
NOT_HISTORY_PATTERN = re.compile(
    r"(?:사용자|관리자|유저|운영자|누군가|상대)(?:가|이)\s|"
    r"(?:바꿨|바꾸었|변경했|수정했|추가했|삭제했|제거했)(?:을\s*때|으면|다면|다고|더라도|는지|을지|을\s*뿐|는데도)"
)
# 장식 배너 (// ====, # ----)
BANNER_COMMENT_PATTERN = re.compile(r"[=\-*#~]{4,}")
# 문장체 끝맺음 (명사형·짧은 구로 끝낸다 — conventions §7)
PROSE_ENDING_PATTERN = re.compile(
    r"(?:합니다|입니다|됩니다|있습니다|없습니다|습니다|하기\s*위해|하기\s*위함|위한\s*것)\s*[.)]?\s*(?:\*/)?\s*$"
)

# 주석 블록이 이 줄 수 이상이면 "긴 블록" (클래스 문서 주석은 2줄 이내 — conventions §7.1)
LONG_COMMENT_BLOCK_LINES = 5
# 주석 처리된 코드 판정: 3줄 이상이고 60% 이상이 코드 모양
COMMENTED_CODE_MINIMUM_LINES = 3
COMMENTED_CODE_RATIO = 0.6
CODE_LIKE_COMMENT_PATTERN = re.compile(
    r"^(?:import |package |from \S+ import |return\b|public |private |protected |static |final |const |let |var |val |"
    r"if\s*\(|for\s*\(|while\s*\(|try\s*\{|\}|@[A-Z]\w*|[\w.$]+\s*\(.*\)\s*;$|</?[A-Z][\w.]*[\s/>])|"
    r";\s*$|\{\s*$|=>\s*[{(]?\s*$|^\s*\w[\w.]*\s*=\s*[^=]")
# 문서 주석: @태그, 파이썬 docstring 절, Javadoc HTML 태그(<p>·<h3>·<ul>)
API_DOC_PATTERN = re.compile(r"@(?:param|return|returns|throws|see|example)\b|^(?:Args|Returns|Raises):|^<(?:p|h\d|ul|ol|li|pre|br)\b")
LICENSE_PATTERN = re.compile(r"license|copyright|\(c\)\s*\d{4}", re.IGNORECASE)

HARDCODED_TOKEN_PATTERNS = {
    "dart": [
        ("color_literal", re.compile(r"\bColor\(0x")),
        ("material_color", re.compile(r"\bColors\.(?!transparent\b)[a-z]\w*")),
        ("spacing_literal", re.compile(r"\bEdgeInsets\.(?:all|symmetric|only|fromLTRB)\([^)]*(?<![\w.])[1-9]")),
        ("sized_box_literal", re.compile(r"\bSizedBox\(\s*(?:height|width):\s*[1-9]")),
        ("font_size_literal", re.compile(r"\bfontSize:\s*[1-9]")),
        ("radius_literal", re.compile(r"\bBorderRadius\.circular\(\s*[1-9]")),
        ("asset_path_literal", re.compile(r"\b(?:Image|SvgPicture)\.asset\(\s*['\"]")),
    ],
    "javascript": [
        ("hex_color", re.compile(r"['\"`](?:#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?|#(?=[0-9]*[a-fA-F])[0-9a-fA-F]{3})\b")),
        ("tailwind_arbitrary_value", re.compile(r"-\[(?:#[0-9a-fA-F]{3,8}|\d+(?:px|rem))\]")),
        ("inline_style", re.compile(r"\bstyle=\{\{")),
        ("asset_path_literal", re.compile(r"\bsrc=\{?\s*[\"'`]/(?:icons?|images?|img|assets|logos?)/")),
    ],
}
HARDCODED_TOKEN_PATTERNS["typescript"] = HARDCODED_TOKEN_PATTERNS["javascript"]
# 토큰 정의 자리 (여기서는 값을 직접 쓰는 것이 정상) — design/ 전체가 아니라 토큰·테마 파일만
TOKEN_DEFINITION_PATH_PATTERN = re.compile(
    r"(?:^|/)(?:themes?|tokens?|colors?|palette)(?:/|\.|_)|(?:^|/)tailwind\.config\.|_(?:colors?|tokens?|theme|spacing|typography)\.\w+$",
    re.IGNORECASE)

# 하드코딩 URL (설정 원본에 둔다 — conventions §5). 스키마·예시·표준 문서 주소는 제외
URL_LITERAL_PATTERN = re.compile(r"[\"'`](https?://[^\"'`\s]+)")
IGNORED_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:w3\.org|example\.(?:com|org)|schemas?\.|json-schema\.org|xmlns|(?:localhost|127\.0\.0\.1)(?::\d+)?(?:/|$))")
# API 문서 예시 속성 (@Schema(example=...)·examples) — 설정이 아니라 문서
DOCUMENTATION_EXAMPLE_PATTERN = re.compile(r"\bexamples?\s*[=:]")

SWALLOWED_CATCH_PATTERNS = {
    "slash": re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}"),
    "python": re.compile(r"\bexcept\b[^:\n]*:\s*(?:#[^\n]*)?\n\s*pass\b|\bexcept\b[^:\n]*:\s*pass\b"),
}
CATCH_START_PATTERNS = {
    "slash": re.compile(r"\bcatch\s*\(([^)]*)\)\s*\{"),
    "python": re.compile(r"^([ \t]*)except\b([^:\n]*):[ \t]*(?:#.*)?$", re.MULTILINE),
}
# 모든 예외를 잡는 catch: Java·Kotlin 최상위 타입, 파이썬 bare·Exception, Dart·JS 타입 없는 catch (on X catch 제외)
TYPED_CATCH_ALL_PATTERN = re.compile(r"^\s*(?:final\s+)?(?:Exception|Throwable|RuntimeException)\b|^\s*\w+\s*:\s*(?:Exception|Throwable)\b")
UNTYPED_CATCH_PATTERN = re.compile(r"^\s*\w+\s*(?:,\s*\w+\s*)?$")
RETHROW_PATTERN = re.compile(r"\b(?:throw|rethrow|raise|return|Result\.|Either\.|Failure\(|emit\()")
# 화면·호출자에 실패를 알림 (에러 상태 설정·에러 콜백·알림 표시 — UI 경계의 정상 처리)
SETS_ERROR_STATE_PATTERN = re.compile(
    r"\bset\w*Error\w*\s*\(|\bon\w*Error\w*\s*[(?.]|completeError|\berror\w*\s*:\s*(?!null\b)|"
    r"\b(?:toast|alert|show\w*(?:Error|Toast|Snack|Dialog)\w*|notify\w*)\s*[.(]", re.IGNORECASE)
# catch 바로 앞 형제 catch 가 잡은 예외를 그대로 던짐 (업무 예외는 이미 통과 — 뒤 catch-all 감싸기는 예외 번역)
PASSTHROUGH_CATCH_PATTERN = re.compile(r"catch\s*\([^)]*\)\s*\{\s*throw\s+\w+\s*;\s*\}\s*$|\n\s*raise\s*\n\s*$")
# 실패를 결과에 담는 건별 처리 (일괄 작업의 정상 패턴 — 흐름이 계속되는 게 의도)
RECORDS_FAILURE_PATTERN = re.compile(r"\.(?:add|put|append|push)\(|isSuccess\(false\)|failReason|\berrors?\[|\bfailures?\b|\bfailed\w*\s*[+=]")
LOGGING_PATTERN = re.compile(r"\b(?:log|logger|LOG|LOGGER|console|print|debugPrint|logging)\b")

# 파일 전체 린트 끄기 (첫 5줄)
LINT_DISABLED_PATTERN = re.compile(
    r"eslint-disable(?!-next-line|-line)(?=\s*(?:\*/|$))|tslint:disable(?!-next-line)(?=\s*(?:\*/|$))|@ts-nocheck|ignore_for_file:|"
    r"#\s*flake8:\s*noqa|#\s*type:\s*ignore|#\s*pylint:\s*disable=all|@SuppressWarnings\(\s*\"all\"\s*\)")


def comment_phrase_findings(content: str) -> list[str]:
    """주석 한 줄의 문제 종류 목록: history / banner / prose_ending"""
    kinds = []
    if HISTORY_COMMENT_PATTERN.search(content) and not NOT_HISTORY_PATTERN.search(content):
        kinds.append("history")
    body = content.lstrip("/#*! ").rstrip("*/ ")
    if BANNER_COMMENT_PATTERN.search(body) and len(re.sub(r"[=\-*#~\s]", "", body)) < len(body) // 2:
        kinds.append("banner")
    if PROSE_ENDING_PATTERN.search(content):
        kinds.append("prose_ending")
    return kinds


def comment_block_kind(start_line: int, contents: list[str]) -> str:
    """주석 블록 성격: license / commented_code / api_doc / prose (판단 단서)"""
    bodies = [c.lstrip("/#*! ").rstrip("*/ ").strip() for c in contents]
    bodies = [b for b in bodies if b]
    if start_line <= 3 and any(LICENSE_PATTERN.search(b) for b in bodies):
        return "license"
    if len(bodies) >= COMMENTED_CODE_MINIMUM_LINES and \
            sum(1 for b in bodies if CODE_LIKE_COMMENT_PATTERN.search(b)) >= len(bodies) * COMMENTED_CODE_RATIO:
        return "commented_code"
    if any(API_DOC_PATTERN.search(b) for b in bodies):
        return "api_doc"
    return "prose"


def hardcoded_tokens_in_line(line: str, language: str, relative_path: str) -> list[str]:
    if TOKEN_DEFINITION_PATH_PATTERN.search(relative_path):
        return []
    return [kind for kind, pattern in HARDCODED_TOKEN_PATTERNS.get(language, []) if pattern.search(line)]


def hardcoded_urls_in_line(line: str) -> list[str]:
    if DOCUMENTATION_EXAMPLE_PATTERN.search(line):
        return []
    return [m.group(1)[:120] for m in URL_LITERAL_PATTERN.finditer(line) if not IGNORED_URL_PATTERN.match(m.group(1))]


def text_block_lines(text: str, language: str) -> set:
    """Java·Kotlin 텍스트 블록(\"\"\" ... \"\"\") 안 줄 번호 (API 문서 예시 JSON 등 — URL 검사에서 뺌)"""
    if language not in ("java", "kotlin"):
        return set()
    inside, numbers = False, set()
    for number, line in enumerate(text.splitlines(), start=1):
        if inside:
            numbers.add(number)
        if line.count('"""') % 2 == 1:
            inside = not inside
    return numbers


def swallowed_catch_findings(text: str, language: str) -> list[dict]:
    """빈 catch·except: pass (has_reason_comment: 같은 줄·바로 위 주석 있음 — 실패해도 되는 정리 코드 단서)"""
    pattern = SWALLOWED_CATCH_PATTERNS["python" if language == "python" else "slash"]
    lines = text.splitlines()
    findings = []
    for match in pattern.finditer(text):
        number = text.count("\n", 0, match.start()) + 1
        nearby = match.group(0) + (lines[number - 2] if number >= 2 else "")
        findings.append({"line": number, "has_reason_comment": "#" in nearby or "//" in nearby})
    return findings


def unhandled_catch_findings(text: str, language: str) -> list[dict]:
    """다시 던지지 않는 catch (본문이 있는데 throw·return·raise 없음) + catch-all 이 다른 예외로 바꿔 던짐

    kind: no_rethrow(흐름이 계속됨 — 롤백·보상 뒤에 계속 진행되는지 본다) / rewrap_all(원래 오류 코드가 사라짐)
    """
    findings = []
    for line_number, caught, body, prefix in _catch_bodies(text, language):
        code = "\n".join(l for l in body.splitlines() if not l.strip().startswith(("//", "#", "*", "/*")))
        if not code.strip() or code.strip() == "pass":
            continue  # 빈 catch 는 swallowed_catch
        is_catch_all = _is_catch_all(caught, language, prefix)
        if not RETHROW_PATTERN.search(code):
            finding = {"line": line_number, "kind": "no_rethrow", "is_catch_all": is_catch_all,
                       "has_log": bool(LOGGING_PATTERN.search(code)), "body_lines": len(body.splitlines())}
            if RECORDS_FAILURE_PATTERN.search(code):
                finding["records_failure"] = True
            if SETS_ERROR_STATE_PATTERN.search(code):
                finding["sets_error_state"] = True
            findings.append(finding)
        elif is_catch_all and re.search(r"\bthrow\s+new\b|\braise\s+\w+\(", code):
            finding = {"line": line_number, "kind": "rewrap_all", "is_catch_all": True,
                       "has_log": bool(LOGGING_PATTERN.search(code)), "body_lines": len(body.splitlines())}
            if PASSTHROUGH_CATCH_PATTERN.search(prefix):
                finding["has_passthrough_before"] = True
            findings.append(finding)
    return findings


def lint_disabled_marker(text: str) -> str | None:
    match = LINT_DISABLED_PATTERN.search("\n".join(text.splitlines()[:5]))
    return match.group(0) if match else None


def _is_catch_all(caught: str, language: str, prefix: str) -> bool:
    if language == "python":
        return not caught or bool(re.match(r"(?:Exception|BaseException)\b", caught))
    if language in ("dart", "javascript", "typescript"):
        return bool(UNTYPED_CATCH_PATTERN.match(caught)) and not re.search(r"\bon\s+[\w<>.]+\s*$", prefix)
    return bool(TYPED_CATCH_ALL_PATTERN.match(caught))


def _catch_bodies(text: str, language: str):
    """(catch 줄 번호, 잡은 타입, 본문, catch 앞 글자) — 중괄호 언어는 괄호 짝, 파이썬은 들여쓰기"""
    if language == "python":
        lines = text.splitlines()
        for match in CATCH_START_PATTERNS["python"].finditer(text):
            number = text.count("\n", 0, match.start()) + 1
            indent = len(match.group(1).expandtabs())
            body = []
            for line in lines[number:]:
                if line.strip() and len(line) - len(line.lstrip()) <= indent:
                    break
                body.append(line)
            yield number, match.group(2).strip(), "\n".join(body), text[max(0, match.start() - 200):match.start()]
        return
    for match in CATCH_START_PATTERNS["slash"].finditer(text):
        depth, index = 1, match.end()
        while index < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[index], 0)
            index += 1
        yield (text.count("\n", 0, match.start()) + 1, match.group(1), text[match.end():index - 1],
               text[max(0, match.start() - 200):match.start()])
