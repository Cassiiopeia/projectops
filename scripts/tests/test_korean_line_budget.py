"""영문 기본 표면의 한글 줄 감시 (#769·#777): 파일별 한글 줄 수 <-> 동결 장부 대조
주석·docstring 은 한국어 규칙이라 세지 않음. 장부 숫자는 줄일 수만 있음 (늘리면 실패)

장부 갱신: python3 scripts/tests/test_korean_line_budget.py --update      (줄어든 숫자만 반영)
처음 만들기: python3 scripts/tests/test_korean_line_budget.py --rebaseline  (전체 재생성 — 리뷰 필수)
"""
import ast
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Dict, List, Optional, Set

import pytest

ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = Path(__file__).with_name("korean_line_budget.json")
HANGUL_RE = re.compile(r"[가-힣ㄱ-ㆎ]")

# 감시 대상: 사용자에게 나가는 영문 기본 표면 (git 추적 파일만)
SCOPE_PREFIXES = (
    "skills/", "plugins/", "scripts/", "src/", "bin/", "hooks/",
    ".github/workflows/", ".github/scripts/", ".github/util/", ".github/ISSUE_TEMPLATE/",
    ".github/DISCUSSION_TEMPLATE/", ".github/config/",
    ".claude-plugin/",
)
SCOPE_FILES = (
    "README.md", "CONTRIBUTING.md", "SECURITY.md", "package.json", ".github/PULL_REQUEST_TEMPLATE.md",
)

# 제외 (정규식, 사유) — 한글이 곧 목적이거나 내부 전용
EXCLUDED_PATTERNS = (
    (r"(^|/)i18n/ko", "한국어 사전·템플릿 폴더"),
    (r"(^|/)[^/]+\.ko\.[^/]+$", "한국어 사본 (*.ko.*)"),
    (r"^src/i18n/[^/]*ko[^/]*$", "CLI 한국어 사전"),
    (r"^\.github/scripts/i18n/ko\.json$", "워크플로 스크립트 한국어 사전"),
    (r"^\.github/config/wizard-prompts\.yml$", "마법사 질문 2개 언어 사전 (*_ko 가 한국어, 영어 원문은 test/wizard-labels.test.js 가 검사)"),
    (r"^\.github/util/.+/[^/]+-i18n\.js$(?<!/wizard-i18n\.js)", "마법사 ko 사전 (en 원문은 check_i18n.py 가 검사, 엔진 wizard-i18n.js 는 셈)"),
    (r"^docs/", "문서 사이트 — /ko/ 를 따로 둠 (#976)"),
    (r"(^|/)CHANGELOG\.[^/]+$", "릴리스 기록 원문"),
    (r"(^|/)CLAUDE\.md$", "내부 에이전트 지침 (한국어)"),
    (r"^skills/pro-launch/troubleshooting/", "검색 키워드가 의도적으로 2개 언어"),
    (r"(^|/)(tests?|__tests__|fixtures|golden)/", "우리 테스트·픽스처·골든"),
    (r"(^|/)conftest\.py$", "우리 pytest 설정"),
    (r"^(?!.*/templates/)(.*/)?(test_[^/]+\.py|[^/]+\.test\.[cm]?js)$", "우리 테스트 (templates/ 안 사용자용 규칙 테스트는 셈)"),
)
EXCLUDED_REGEXES = tuple((re.compile(pattern), reason) for pattern, reason in EXCLUDED_PATTERNS)

# 파일 종류 판정 (.template·.tmpl·.example 는 벗기고 안쪽 확장자로, Fastfile.ios 처럼 이름 앞부분도 봄)
WRAPPER_SUFFIXES = (".template", ".tmpl", ".example")
HASH_COMMENT_SUFFIXES = {".sh", ".bash", ".yaml", ".yml", ".toml", ".ps1", ".rb"}
HASH_COMMENT_NAMES = {"Fastfile", "Gemfile", "Podfile", "Appfile", "Dockerfile", ".gitignore"}
C_LIKE_SUFFIXES = {".js", ".mjs", ".cjs", ".ts", ".mts", ".java", ".dart", ".kt", ".gradle", ".swift"}
MARKUP_SUFFIXES = {".html", ".htm", ".xml", ".plist", ".svg", ".md"}
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
# 줄 주석 표식 앞에 와도 되는 문자 (https:// 같은 URL·${#var} 배제)
MARKER_PRECEDERS = set(" \t;,(){}")


def is_excluded(relative: str) -> Optional[str]:
    for regex, reason in EXCLUDED_REGEXES:
        if regex.search(relative):
            return reason
    return None


def is_in_scope(relative: str) -> bool:
    return relative in SCOPE_FILES or relative.startswith(SCOPE_PREFIXES)


def list_counted_files() -> List[str]:
    """git 추적 파일 > 범위 안 > 제외 목록 밖"""
    output = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8")
    return sorted(
        relative for relative in output.split("\0")
        if relative and is_in_scope(relative) and not is_excluded(relative)
    )


def detect_file_kind(relative: str) -> str:
    name = relative.rsplit("/", 1)[-1]
    for wrapper in WRAPPER_SUFFIXES:
        if name.endswith(wrapper):
            name = name[: -len(wrapper)]
    suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if suffix == ".py":
        return "python"
    if suffix in HASH_COMMENT_SUFFIXES or name.split(".")[0] in HASH_COMMENT_NAMES:
        return "hash"
    if suffix in C_LIKE_SUFFIXES:
        return "c-like"
    if suffix == ".css":
        return "css"
    if suffix in MARKUP_SUFFIXES:
        return "markup"
    return "raw"


# ── 주석 제거: 종류별로 주석 자리를 비운 줄 목록을 돌려줌 (줄 번호 유지) ──

def blank_html_comments(text: str) -> str:
    """<!-- --> 를 같은 줄 수의 빈 줄로"""
    return re.sub(r"<!--.*?-->", lambda match: "\n" * match.group(0).count("\n"), text, flags=re.DOTALL)


def strip_hash_comments(lines: List[str], also_double_slash: bool) -> List[str]:
    """# 주석 제거 (따옴표 안·URL 조각 제외), heredoc 본문은 그대로 둠"""
    code_lines = []
    heredoc_terminator = None
    for line in lines:
        if heredoc_terminator is not None:
            code_lines.append(line)
            if line.strip() == heredoc_terminator:
                heredoc_terminator = None
            continue
        markers = ("#", "//") if also_double_slash else ("#",)
        code = cut_at_line_marker(line, markers)
        heredoc_match = HEREDOC_RE.search(code)
        if heredoc_match:
            heredoc_terminator = heredoc_match.group(2)
        code_lines.append(code)
    return code_lines


def cut_at_line_marker(line: str, markers: tuple) -> str:
    """한 줄 안 따옴표 밖 첫 줄 주석 표식 앞까지"""
    quote = None
    index = 0
    while index < len(line):
        character = line[index]
        if quote:
            if character == "\\":
                index += 1
            elif character == quote:
                quote = None
        elif character == '"' or (character == "'" and not (index and line[index - 1].isalnum())):
            quote = character
        elif any(line.startswith(marker, index) for marker in markers) and (
            index == 0 or line[index - 1] in MARKER_PRECEDERS
        ):
            return line[:index]
        index += 1
    return line


def strip_c_like_comments(text: str, has_line_comments: bool) -> List[str]:
    """// · /* */ 제거, 문자열('" 한 줄 · ` 여러 줄 + ${} 중첩) 안은 유지"""
    output = []
    quote = None
    # 템플릿 리터럴 스택: "template" = 본문, 정수 = ${} 식 안 중괄호 깊이
    template_stack: list = []
    in_block_comment = False
    index = 0
    while index < len(text):
        character = text[index]
        if character == "\n" and not in_block_comment:
            quote = None
        if in_block_comment:
            if text.startswith("*/", index):
                in_block_comment = False
                index += 2
                continue
            if character == "\n":
                output.append(character)
            index += 1
            continue
        if quote or (template_stack and template_stack[-1] == "template"):
            if character == "\\":
                output.append(text[index:index + 2])
                index += 2
                continue
            if quote and character == quote:
                quote = None
            elif not quote and character == "`":
                template_stack.pop()
            elif not quote and text.startswith("${", index):
                template_stack.append(0)
                output.append("${")
                index += 2
                continue
            output.append(character)
            index += 1
            continue
        if character == "`":
            template_stack.append("template")
        elif character == '"' or (character == "'" and not (index and text[index - 1].isalnum())):
            quote = character
        elif template_stack and character == "{":
            template_stack[-1] += 1
        elif template_stack and character == "}":
            if template_stack[-1] == 0:
                template_stack.pop()
            else:
                template_stack[-1] -= 1
        elif text.startswith("/*", index):
            in_block_comment = True
            index += 2
            continue
        elif has_line_comments and text.startswith("//", index) and (
            index == 0 or text[index - 1] in MARKER_PRECEDERS or text[index - 1] == "\n"
        ):
            line_end = text.find("\n", index)
            index = len(text) if line_end == -1 else line_end
            continue
        elif has_line_comments and character == "/" and is_regex_literal_start(output):
            regex_end = find_regex_literal_end(text, index)
            output.append(text[index:regex_end])
            index = regex_end
            continue
        output.append(character)
        index += 1
    return "".join(output).split("\n")


def is_regex_literal_start(output: List[str]) -> bool:
    """/ 앞 마지막 코드 문자가 연산자·여는 괄호면 나눗셈이 아니라 정규식 (/'/g 의 따옴표 오판 방지)"""
    preceding = "".join(output[-40:]).rstrip(" \t")
    return not preceding or preceding[-1] in "(,=:[!&|?{};\n" or preceding.endswith("return")


def find_regex_literal_end(text: str, start: int) -> int:
    """정규식 끝 / 다음 위치 (문자 클래스·이스케이프 고려, 줄 끝이면 거기서 멈춤)"""
    index = start + 1
    in_class = False
    while index < len(text) and text[index] != "\n":
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if character == "[":
            in_class = True
        elif character == "]":
            in_class = False
        elif character == "/" and not in_class:
            return index + 1
        index += 1
    return index


def collect_python_docstring_starts(text: str) -> Set[tuple]:
    """모듈·클래스·함수 첫 문자열 문 위치 (줄, 열)"""
    try:
        module = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    starts = set()
    for node in ast.walk(module):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                starts.add((first.value.lineno, first.value.col_offset))
    return starts


def find_python_korean_lines(text: str) -> Optional[Set[int]]:
    """tokenize: COMMENT·docstring 제외 토큰에서 한글이 든 물리 줄 (실패 시 None)"""
    docstring_starts = collect_python_docstring_starts(text)
    korean_lines: Set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT or (token.type == tokenize.STRING and token.start in docstring_starts):
                continue
            for offset, segment in enumerate(token.string.split("\n")):
                if HANGUL_RE.search(segment):
                    korean_lines.add(token.start[0] + offset)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    return korean_lines


def count_korean_code_lines(relative: str, text: str) -> int:
    text = text.replace("\r\n", "\n")
    kind = detect_file_kind(relative)
    if kind == "python":
        python_lines = find_python_korean_lines(text)
        if python_lines is not None:
            return len(python_lines)
        kind = "hash"
    if kind == "hash":
        is_yaml = relative.endswith((".yaml", ".yml"))
        code_lines = strip_hash_comments(text.split("\n"), also_double_slash=is_yaml)
    elif kind == "c-like":
        code_lines = strip_c_like_comments(text, has_line_comments=True)
    elif kind == "css":
        code_lines = strip_c_like_comments(text, has_line_comments=False)
    elif kind == "markup":
        code_lines = blank_html_comments(text).split("\n")
    else:
        code_lines = text.split("\n")
    return sum(1 for line in code_lines if HANGUL_RE.search(line))


def measure_korean_line_counts() -> Dict[str, int]:
    """대상 파일별 한글 줄 수 (0 인 파일·이진 파일 제외)"""
    counts = {}
    for relative in list_counted_files():
        try:
            text = (ROOT / relative).read_bytes().decode("utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        count = count_korean_code_lines(relative, text)
        if count:
            counts[relative] = count
    return counts


def read_ledger() -> Dict[str, int]:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))["files"]


def write_ledger(counts: Dict[str, int]) -> None:
    ledger = {
        "_about": "Hangul non-comment lines per file (#769). Numbers may only go down. "
                  "Regenerate lowered numbers: python3 scripts/tests/test_korean_line_budget.py --update",
        "total": sum(counts.values()),
        "files": dict(sorted(counts.items())),
    }
    LEDGER_PATH.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_git_available() -> bool:
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT, capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


# ── 판정 ──

@pytest.mark.skipif(not is_git_available(), reason="git 작업 트리 아님 (추적 파일 목록 필요)")
def test_korean_lines_never_grow_on_english_surfaces():
    """새 파일 한글 0 · 기존 파일 장부 이하 · 줄었으면 장부도 낮추라고 실패"""
    ledger = read_ledger()
    measured = measure_korean_line_counts()

    grown = [
        f"{relative}: {count}줄 (장부 {ledger.get(relative, 0)})"
        for relative, count in sorted(measured.items()) if count > ledger.get(relative, 0)
    ]
    assert not grown, (
        "영문 기본 표면에 한글 줄이 늘었다 (주석·docstring 은 안 셈). 문구는 영어로 쓰고 "
        "한국어는 i18n ko 사전에 넣는다. 코드가 대조하는 데이터라 꼭 한글이어야 하면 "
        "리뷰에서 이유를 밝히고 장부 숫자를 직접 올린다:\n  " + "\n  ".join(grown)
    )

    lowered = [
        f"{relative}: 장부 {budget} > 실제 {measured.get(relative, 0)}"
        for relative, budget in sorted(ledger.items()) if measured.get(relative, 0) < budget
    ]
    assert not lowered, (
        "한글 줄이 줄었다 — 장부를 낮춘다: python3 scripts/tests/test_korean_line_budget.py --update\n  "
        + "\n  ".join(lowered)
    )


def test_comment_and_docstring_lines_are_not_counted():
    """스캐너 계약: 주석·docstring 제외, 문자열·문서 본문은 셈"""
    python_source = '"""모듈 설명"""\n# 주석\nlabel = "한글"  # 꼬리 주석\ndef run():\n    """함수 설명"""\n    return f"값 {label} 끝"\n'
    assert count_korean_code_lines("a.py", python_source) == 2
    shell_source = 'echo "한글 # 안 잘림"\n# 주석\nurl=https://x.y/#한글\ncat <<EOF\n# 본문 한글\nEOF\n'
    assert count_korean_code_lines("a.sh", shell_source) == 3
    yaml_source = "name: Build  # 빌드\nrun: |\n  // 스크립트 주석\n  core.info('완료')\n"
    assert count_korean_code_lines("a.yaml", yaml_source) == 1
    script_source = "// 주석\nconst a = '한글'; /* 블록\n주석 */\nconst b = `여러\n줄`;\n"
    assert count_korean_code_lines("a.js", script_source) == 3
    nested_template_source = "const c = `${x.map((y) => `${y}`)}`;\nconst e = s.replace(/'/g, `'\\\\''`);\n// 주석\nconst d = '값';\n"
    assert count_korean_code_lines("a.js", nested_template_source) == 1
    markdown_source = "<!-- 숨김\n주석 -->\n# 제목 한글\n"
    assert count_korean_code_lines("a.md", markdown_source) == 1


def test_exclusions_keep_engine_but_drop_dictionaries():
    assert is_excluded(".github/util/flutter/playstore-wizard/playstore-wizard-i18n.js")
    assert not is_excluded(".github/util/flutter/_shared/wizard-i18n.js")
    assert is_excluded("src/i18n/core.ko.js") and not is_excluded("src/i18n/core.en.js")
    assert is_excluded("skills/pro-launch/tests/test_app.py")
    assert not is_excluded("plugins/projectops-extras/skills/pro-code-consult/templates/rule-tests/python/test_architecture_rules.py.tmpl")
    assert is_excluded(".github/config/wizard-prompts.yml")
    assert is_in_scope(".github/config/issue-labels.yml") and not is_excluded(".github/config/issue-labels.yml")
    assert is_in_scope(".github/DISCUSSION_TEMPLATE/documents.yaml")
    assert is_excluded(".github/i18n/ko/DISCUSSION_TEMPLATE/documents.yaml")


def update_ledger(allow_increase: bool) -> None:
    """--update: 줄어든 숫자만 반영 / --rebaseline: 전체 재생성"""
    measured = measure_korean_line_counts()
    if allow_increase:
        write_ledger(measured)
        return
    ledger = read_ledger()
    lowered = {relative: min(budget, measured.get(relative, 0)) for relative, budget in ledger.items()}
    write_ledger({relative: count for relative, count in lowered.items() if count})


if __name__ == "__main__":
    if "--rebaseline" in sys.argv:
        update_ledger(allow_increase=True)
    elif "--update" in sys.argv:
        update_ledger(allow_increase=False)
    else:
        sys.exit("usage: test_korean_line_budget.py --update | --rebaseline")
    print(f"wrote {LEDGER_PATH.relative_to(ROOT)}")
