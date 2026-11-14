"""Watch Korean lines on English-default surfaces (#769·#777): Korean line count per file <-> frozen ledger
Comments and docstrings are not counted. Ledger numbers can only go down (growth fails)

Update ledger: python3 scripts/tests/test_korean_line_budget.py --update      (applies only lowered counts)
Create from scratch: python3 scripts/tests/test_korean_line_budget.py --rebaseline  (full regeneration — review required)
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

# Watched: user-facing English-default surfaces (git-tracked files only)
SCOPE_PREFIXES = (
    "skills/", "plugins/", "scripts/", "src/", "bin/", "hooks/",
    ".github/workflows/", ".github/scripts/", ".github/util/", ".github/ISSUE_TEMPLATE/",
    ".github/DISCUSSION_TEMPLATE/", ".github/config/",
    ".claude-plugin/",
)
SCOPE_FILES = (
    "README.md", "CONTRIBUTING.md", "SECURITY.md", "package.json", ".github/PULL_REQUEST_TEMPLATE.md",
)

# Exclusions (regex, reason) — Korean is the purpose, or internal only
EXCLUDED_PATTERNS = (
    (r"(^|/)i18n/ko", "Korean catalogs and template folders"),
    (r"(^|/)[^/]+\.ko\.[^/]+$", "Korean copies (*.ko.*)"),
    (r"^src/i18n/[^/]*ko[^/]*$", "CLI Korean catalog"),
    (r"^\.github/scripts/i18n/ko\.json$", "Workflow script Korean catalog"),
    (r"^\.github/config/wizard-prompts\.yml$", "Bilingual wizard prompt catalog (*_ko is Korean; English source checked by test/wizard-labels.test.js)"),
    (r"^\.github/util/.+/[^/]+-i18n\.js$(?<!/wizard-i18n\.js)", "Wizard ko catalog (en source checked by check_i18n.py; the wizard-i18n.js engine is counted)"),
    (r"^docs/", "Docs site — has a separate /ko/ (#976)"),
    (r"(^|/)CHANGELOG\.[^/]+$", "Release history source"),
    (r"(^|/)CLAUDE\.md$", "Internal agent instructions (Korean)"),
    (r"^skills/pro-launch/troubleshooting/", "Search keywords are intentionally bilingual"),
    (r"(^|/)(tests?|__tests__|fixtures|golden)/", "Our tests, fixtures and goldens"),
    (r"(^|/)conftest\.py$", "Our pytest config"),
    (r"^(?!.*/templates/)(.*/)?(test_[^/]+\.py|[^/]+\.test\.[cm]?js)$", "Our tests (user-facing rule tests under templates/ are counted)"),
)
EXCLUDED_REGEXES = tuple((re.compile(pattern), reason) for pattern, reason in EXCLUDED_PATTERNS)

# Line-level exclusion: only "*_ko" JSON key lines are skipped (the English key of the same entry still counts)
# breaking-changes.json: title/message English source + title_ko/message_ko Korean (#988, English source checked by test/breaking.test.js)
KOREAN_SIBLING_KEY_RE = re.compile(r'^\s*"[A-Za-z0-9_]+_ko"\s*:')
KOREAN_SIBLING_KEY_FILES = {".github/config/breaking-changes.json"}

# File kind detection (strip .template/.tmpl/.example and use the inner extension; also checks the name prefix, e.g. Fastfile.ios)
WRAPPER_SUFFIXES = (".template", ".tmpl", ".example")
HASH_COMMENT_SUFFIXES = {".sh", ".bash", ".yaml", ".yml", ".toml", ".ps1", ".rb"}
HASH_COMMENT_NAMES = {"Fastfile", "Gemfile", "Podfile", "Appfile", "Dockerfile", ".gitignore"}
C_LIKE_SUFFIXES = {".js", ".mjs", ".cjs", ".ts", ".mts", ".java", ".dart", ".kt", ".gradle", ".swift"}
MARKUP_SUFFIXES = {".html", ".htm", ".xml", ".plist", ".svg", ".md"}
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
# Characters allowed before a line-comment marker (rules out URLs like https:// and ${#var})
MARKER_PRECEDERS = set(" \t;,(){}")


def is_excluded(relative: str) -> Optional[str]:
    for regex, reason in EXCLUDED_REGEXES:
        if regex.search(relative):
            return reason
    return None


def is_in_scope(relative: str) -> bool:
    return relative in SCOPE_FILES or relative.startswith(SCOPE_PREFIXES)


def list_counted_files() -> List[str]:
    """git-tracked files > in scope > not excluded"""
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


# ── Comment stripping: returns lines with comment spans blanked per kind (line numbers kept) ──

def blank_html_comments(text: str) -> str:
    """<!-- --> to the same number of blank lines"""
    return re.sub(r"<!--.*?-->", lambda match: "\n" * match.group(0).count("\n"), text, flags=re.DOTALL)


def strip_hash_comments(lines: List[str], also_double_slash: bool) -> List[str]:
    """Strip # comments (except inside quotes and URL fragments); heredoc bodies stay as is"""
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
    """Up to the first line-comment marker outside quotes on one line"""
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
    """Strip // and /* */, keeping string contents ('" single-line, ` multi-line with nested ${})"""
    output = []
    quote = None
    # Template literal stack: "template" = body, integer = brace depth inside a ${} expression
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
    """A / after an operator or opening bracket is a regex, not division (avoids misreading the quote in /'/g)"""
    preceding = "".join(output[-40:]).rstrip(" \t")
    return not preceding or preceding[-1] in "(,=:[!&|?{};\n" or preceding.endswith("return")


def find_regex_literal_end(text: str, start: int) -> int:
    """Position after the closing / of a regex (handles character classes and escapes; stops at end of line)"""
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
    """Positions (line, column) of the first string statement in modules, classes and functions"""
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
    """tokenize: physical lines with Korean in tokens other than COMMENT and docstrings (None on failure)"""
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
    if relative in KOREAN_SIBLING_KEY_FILES:
        code_lines = [line for line in code_lines if not KOREAN_SIBLING_KEY_RE.match(line)]
    return sum(1 for line in code_lines if HANGUL_RE.search(line))


def measure_korean_line_counts() -> Dict[str, int]:
    """Korean line count per target file (files with 0 and binary files omitted)"""
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


# ── Verdict ──

@pytest.mark.skipif(not is_git_available(), reason="not a git work tree (tracked file list required)")
def test_korean_lines_never_grow_on_english_surfaces():
    """New files have 0 Korean · existing files stay within the ledger · fail on a drop too so the ledger gets lowered"""
    ledger = read_ledger()
    measured = measure_korean_line_counts()

    grown = [
        f"{relative}: {count} lines (ledger {ledger.get(relative, 0)})"
        for relative, count in sorted(measured.items()) if count > ledger.get(relative, 0)
    ]
    assert not grown, (
        "Korean lines grew on an English-default surface (comments and docstrings are not counted). Write text in English "
        "and put Korean in the i18n ko catalog. If it must be Korean because code compares it, "
        "explain why in review and raise the ledger number by hand:\n  " + "\n  ".join(grown)
    )

    lowered = [
        f"{relative}: ledger {budget} > actual {measured.get(relative, 0)}"
        for relative, budget in sorted(ledger.items()) if measured.get(relative, 0) < budget
    ]
    assert not lowered, (
        "Korean lines dropped — lower the ledger: python3 scripts/tests/test_korean_line_budget.py --update\n  "
        + "\n  ".join(lowered)
    )


def test_comment_and_docstring_lines_are_not_counted():
    """Scanner contract: comments and docstrings skipped, strings and document bodies counted"""
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
    assert not is_excluded("skills/pro-code-consult/templates/rule-tests/python/test_architecture_rules.py.tmpl")
    assert is_excluded(".github/config/wizard-prompts.yml")
    assert is_in_scope(".github/config/issue-labels.yml") and not is_excluded(".github/config/issue-labels.yml")
    assert is_in_scope(".github/DISCUSSION_TEMPLATE/documents.yaml")
    assert is_excluded(".github/i18n/ko/DISCUSSION_TEMPLATE/documents.yaml")


def test_korean_sibling_keys_skip_only_ko_lines():
    """breaking-changes.json: only *_ko key lines skipped, Korean inside English keys is counted (#988)"""
    registry_source = '{\n  "1.0.0": {\n    "title": "제목",\n    "title_ko": "제목",\n    "message_ko": "본문"\n  }\n}\n'
    assert count_korean_code_lines(".github/config/breaking-changes.json", registry_source) == 1
    assert count_korean_code_lines(".github/config/other.json", registry_source) == 3


def update_ledger(allow_increase: bool) -> None:
    """--update: apply only lowered counts / --rebaseline: full regeneration"""
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
