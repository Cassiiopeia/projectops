"""Line- and file-level smell detection (shared by scan and diff): comment wording and blocks, hardcoded tokens and URLs, catch handling, lint disables

No verdicts — only candidates and judgment hints (tags). The agent filters false positives by reading the source.
Naming smells live in naming_smells; cross-file smells (bypasses, duplicate constants, long functions) in structure_smells.
"""
from __future__ import annotations

import re

from .naming_smells import (boolean_function_names_in_line, boolean_names_in_line,  # noqa: F401 — diff_review compatibility
                            file_type_name_mismatch, naming_findings_in_line, without_string_literals)

# History comments (work history belongs in commits and issues — conventions §7.6)
# Noun-form endings (추가함, 삭제함) also describe current behavior (the form conventions §7 recommends), so they are not included
HISTORY_COMMENT_PATTERN = re.compile(
    r"기존에는|예전(?:에는|엔)|원래는|이전에는|이제는|"
    r"리팩터링으로|리팩토링으로|이전\s*버그|문제가\s*있었|그대로\s*옮(?:겼|김)|통합\s*후|"
    r"기존\s*\S*\s*(?:방식|메서드|로직|버전)|기존\s*\S+\s*(?:→|->)|에서\s*(?:\S+\s*(?:으로|로)\s*)?전환|"
    r"(?:으로|로)\s*(?:변경|통합|교체)(?:했|함|되었|됐)|"
    r"\bpreviously\b|(?<!is )(?<!are )(?<!be )(?<!was )(?<!were )(?<!been )(?<!being )\bused to\b|"
    r"\bno longer\b|\bnow uses?\b|\bwas changed\b|\brefactored\b|"
    r"\bchanged from\b|\bfixed (?:a |the )?bug\b|\bold (?:code|logic|version|behavior)\b|\bmigrated from\b",
    re.IGNORECASE,
)
# Weak wording: a past-tense verb alone also describes domain events ("비밀번호를 변경했다" password changed, "양식이 바뀌었다" form changed)
WEAK_HISTORY_COMMENT_PATTERN = re.compile(
    r"바꿨|바꾸었|(?<!줄)바꿈(?![가-힣])|변경했|수정했|고쳤|추가했|제거했|삭제했|옮겼|걷어냈|없앴|되돌렸|뒤집었|바뀌었|통일했|통일함")
# Not history: user/admin actions, assumptions, conditions, questions ("관리자가 바꿨을 때", "바뀌었나", "고쳤는데 깨진다")
NOT_HISTORY_PATTERN = re.compile(
    r"(?:사용자|관리자|유저|운영자|누군가|상대)(?:가|이)\s|"
    r"(?:바꿨|바꾸었|변경했|수정했|추가했|삭제했|제거했|고쳤|바뀌었|옮겼|되돌렸)(?:을|는지|어도|나[\s.?」)]|나$|는데|으면|다면|다고|더라도|을지)"
)
# Decorative banners (// ====, # ----)
BANNER_COMMENT_PATTERN = re.compile(r"[=\-*#~]{4,}")
# Full-sentence endings (end with a noun form or short phrase — conventions §7)
PROSE_ENDING_PATTERN = re.compile(
    r"(?:합니다|입니다|됩니다|있습니다|없습니다|습니다|하기\s*위해|하기\s*위함|위한\s*것)\s*[.)]?\s*(?:\*/)?\s*$"
)

# A comment block this long or longer is a "long block" (class doc comments stay within 2 lines — conventions §7.1)
LONG_COMMENT_BLOCK_LINES = 5
# Commented-out code: 3+ lines with 60%+ looking like code
COMMENTED_CODE_MINIMUM_LINES = 3
COMMENTED_CODE_RATIO = 0.6
CODE_LIKE_COMMENT_PATTERN = re.compile(
    r"^(?:import |package |from \S+ import |return\b|public |private |protected |static |final |const |let |var |val |"
    r"if\s*\(|for\s*\(|while\s*\(|try\s*\{|\}|@[A-Z]\w*|[\w.$]+\s*\(.*\)\s*;$|</?[A-Z][\w.]*[\s/>])|"
    r";\s*$|\{\s*$|=>\s*[{(]?\s*$|^\s*\w[\w.]*\s*=\s*[^=]|"
    r"^[^가-힣]*[\w)\]\"'][,+]\s*$")
# Doc comments: @tags, Python docstring sections, Javadoc HTML tags (<p>, <h3>, <ul>)
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
# Token definition files (raw values are normal here) — only token/theme files, not all of design/
TOKEN_DEFINITION_PATH_PATTERN = re.compile(
    r"(?:^|/)(?:themes?|tokens?|colors?|palette)(?:/|\.|_)|(?:^|/)tailwind\.config\.|_(?:colors?|tokens?|theme|spacing|typography)\.\w+$",
    re.IGNORECASE)

# Hardcoded URLs (belong in the config source — conventions §5). Schema, example and standards-doc URLs excluded
URL_LITERAL_PATTERN = re.compile(r"[\"'`](https?://[^\"'`\s]+)")
IGNORED_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:$|w3\.org|example\.(?:com|org)|schemas?\.|json-schema\.org|xmlns|(?:localhost|127\.0\.0\.1)(?::\d+)?(?:/|$))")
# API doc example attributes (@Schema(example=...), examples) — documentation, not config
DOCUMENTATION_EXAMPLE_PATTERN = re.compile(r"\bexamples?\s*[=:]")

SWALLOWED_CATCH_PATTERNS = {
    "slash": re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}"),
    "python": re.compile(r"\bexcept\b[^:\n]*:\s*(?:#[^\n]*)?\n\s*pass\b|\bexcept\b[^:\n]*:\s*pass\b"),
}
CATCH_START_PATTERNS = {
    "slash": re.compile(r"\bcatch\s*\(([^)]*)\)\s*\{"),
    "python": re.compile(r"^([ \t]*)except\b([^:\n]*):[ \t]*(?:#.*)?$", re.MULTILINE),
}
# Catch-all: Java/Kotlin top-level types, Python bare/Exception, untyped Dart/JS catch (on X catch excluded)
TYPED_CATCH_ALL_PATTERN = re.compile(r"^\s*(?:final\s+)?(?:Exception|Throwable|RuntimeException)\b|^\s*\w+\s*:\s*(?:Exception|Throwable)\b")
UNTYPED_CATCH_PATTERN = re.compile(r"^\s*\w+\s*(?:,\s*\w+\s*)?$")
RETHROW_PATTERN = re.compile(r"\b(?:throw|rethrow|raise|return|Result\.|Either\.|Failure\(|emit\()")
# Reports failure to the screen or caller (error state, error callback, notice — normal handling at the UI boundary)
SETS_ERROR_STATE_PATTERN = re.compile(
    r"\bset\w*Error\w*\s*\(|\bon\w*Error\w*\s*[(?.]|completeError|\berror\w*\s*:\s*(?!null\b)|"
    r"\b(?:toast|alert|show\w*(?:Error|Toast|Snack|Dialog)\w*|notify\w*)\s*[.(]", re.IGNORECASE)
# The sibling catch right before rethrows its exception as-is (business exceptions pass through — the later catch-all wrap is exception translation)
PASSTHROUGH_CATCH_PATTERN = re.compile(r"catch\s*\([^)]*\)\s*\{\s*throw\s+\w+\s*;\s*\}\s*$|\n\s*raise\s*\n\s*$")
# Per-item handling that records failure in the result (normal batch pattern — continuing is intended)
RECORDS_FAILURE_PATTERN = re.compile(r"\.(?:add|put|append|push)\(|isSuccess\(false\)|failReason|\berrors?\[|\bfailures?\b|\bfailed\w*\s*[+=]")
# Exceptions thrown directly in the try body (hint for whether a catch-all swallows them into another exception)
THROWS_IN_TRY_PATTERN = re.compile(r"\bthrow\s+new\b|\braise\s+\w+")
LOGGING_PATTERN = re.compile(r"\b(?:log|logger|LOG|LOGGER|console|print|debugPrint|logging)\b")

# Whole-file lint disables (first 5 lines)
LINT_DISABLED_PATTERN = re.compile(
    r"eslint-disable(?!-next-line|-line)(?=\s*(?:\*/|$))|tslint:disable(?!-next-line)(?=\s*(?:\*/|$))|@ts-nocheck|ignore_for_file:|"
    r"#\s*flake8:\s*noqa|#\s*type:\s*ignore|#\s*pylint:\s*disable=all|@SuppressWarnings\(\s*\"all\"\s*\)")


def comment_phrase_findings(content: str) -> list[str]:
    """Issue kinds for one comment line: history / banner / prose_ending"""
    kinds = []
    if not NOT_HISTORY_PATTERN.search(content):
        is_one_line_doc = content.startswith("/**") and content.endswith("*/")
        if HISTORY_COMMENT_PATTERN.search(content) or (WEAK_HISTORY_COMMENT_PATTERN.search(content) and not is_one_line_doc):
            kinds.append("history")
    body = content.lstrip("/#*! ").rstrip("*/ ")
    if BANNER_COMMENT_PATTERN.search(body) and len(re.sub(r"[=\-*#~\s]", "", body)) < len(body) // 2:
        kinds.append("banner")
    if PROSE_ENDING_PATTERN.search(content):
        kinds.append("prose_ending")
    return kinds


def comment_block_kind(start_line: int, contents: list[str]) -> str:
    """Comment block kind: license / commented_code / api_doc / prose (judgment hint)"""
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


EXAMPLE_BLOCK_OPEN_PATTERN = re.compile(r"[\"']examples?[\"']\s*:\s*[\[{(]|\bexamples?\s*=\s*[\[{(]|\b(?:json_schema_extra|schema_extra)\b")
TEXT_BLOCK_DELIMITERS = {"java": ('"""',), "kotlin": ('"""',), "python": ('"""', "'''"), "dart": ('"""', "'''")}


def embedded_text_lines(text: str, language: str) -> set:
    """Line numbers inside non-code strings and doc examples: multi-line strings (text blocks, triple quotes) and example(s) blocks

    They hold API doc example JSON and other-language scripts (browser JS, SQL) — excluded from URL and name checks.
    """
    numbers = set()
    delimiters = TEXT_BLOCK_DELIMITERS.get(language, ())
    open_delimiter = None
    depth = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if open_delimiter:
            numbers.add(number)
            if line.count(open_delimiter) % 2 == 1:
                open_delimiter = None
            continue
        if depth > 0:
            numbers.add(number)
            depth += sum(line.count(c) for c in "[{(") - sum(line.count(c) for c in "]})")
            continue
        for delimiter in delimiters:
            if line.count(delimiter) % 2 == 1:
                open_delimiter = delimiter
                break
        match = EXAMPLE_BLOCK_OPEN_PATTERN.search(line)
        if match and not open_delimiter:
            depth = sum(line[match.start():].count(c) for c in "[{(") - sum(line[match.start():].count(c) for c in "]})")
            depth = max(depth, 0)
    return numbers


def swallowed_catch_findings(text: str, language: str) -> list[dict]:
    """Empty catch / except: pass (has_reason_comment: comment on the same line or just above — hint of cleanup code allowed to fail)"""
    pattern = SWALLOWED_CATCH_PATTERNS["python" if language == "python" else "slash"]
    lines = text.splitlines()
    findings = []
    for match in pattern.finditer(text):
        number = text.count("\n", 0, match.start()) + 1
        nearby = match.group(0) + (lines[number - 2] if number >= 2 else "")
        findings.append({"line": number, "has_reason_comment": "#" in nearby or "//" in nearby})
    return findings


def unhandled_catch_findings(text: str, language: str) -> list[dict]:
    """Catch that does not rethrow (has a body but no throw/return/raise) + catch-all that rethrows as a different exception

    kind: no_rethrow (flow continues — check whether it proceeds after rollback/compensation) / rewrap_all (the original error code is lost)
    """
    findings = []
    for line_number, caught, body, prefix in _catch_bodies(text, language):
        code = "\n".join(l for l in body.splitlines() if not l.strip().startswith(("//", "#", "*", "/*")))
        if not code.strip() or code.strip() == "pass":
            continue  # empty catch is swallowed_catch
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
            if THROWS_IN_TRY_PATTERN.search(_try_body_before(text, language, line_number)):
                finding["try_body_throws"] = True
            findings.append(finding)
    return findings


def lint_disabled_marker(text: str) -> str | None:
    match = LINT_DISABLED_PATTERN.search("\n".join(text.splitlines()[:5]))
    return match.group(0) if match else None


def _try_body_before(text: str, language: str, catch_line: int) -> str:
    """From the start of the try right before the catch up to the catch line (nearest try)"""
    through_line = "\n".join(text.splitlines()[:catch_line])
    before = through_line[:max(through_line.rfind("except" if language == "python" else "catch"), 0)]
    start = before.rfind("try:" if language == "python" else "try")
    return before[start:] if start >= 0 else ""


def _is_catch_all(caught: str, language: str, prefix: str) -> bool:
    if language == "python":
        return not caught or bool(re.match(r"(?:Exception|BaseException)\b", caught))
    if language in ("dart", "javascript", "typescript"):
        return bool(UNTYPED_CATCH_PATTERN.match(caught)) and not re.search(r"\bon\s+[\w<>.]+\s*$", prefix)
    return bool(TYPED_CATCH_ALL_PATTERN.match(caught))


def _catch_bodies(text: str, language: str):
    """(catch line number, caught type, body, text before catch) — brace matching for brace languages, indentation for Python"""
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
