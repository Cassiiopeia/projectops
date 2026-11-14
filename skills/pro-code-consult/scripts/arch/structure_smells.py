"""Cross-file smells (scan only): long functions, bypassed shared entry points and extraction candidates, duplicate same-value constants

All are candidates. Bypasses come with evidence that a shared entry point already exists (wrappers); without one they are rule-of-three candidates.
"""
from __future__ import annotations

import re

from .naming_smells import without_string_literals

# Long functions (a sign of mixed steps — conventions §3.3 and the first row of §8)
LONG_FUNCTION_LINES = 60
CONTROL_KEYWORDS = {"if", "for", "while", "switch", "catch", "synchronized", "return", "new", "else", "try", "do",
                    "when", "foreach", "using", "class", "interface", "enum", "record", "object", "with", "super", "this"}
SLASH_FUNCTION_START_PATTERNS = (
    re.compile(r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:[\w<>\[\],.?]+\s+)*([A-Za-z_$][\w$]*)\s*\([^;]*\)\s*"
               r"(?:async\*?\s*|throws\s+[\w., ]+\s*|:\s*[\w<>\[\]|?,. ]+\s*)?\{\s*$"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*[^=]+)?=>\s*\{\s*$"),
)
PYTHON_FUNCTION_START_PATTERN = re.compile(r"^([ \t]*)(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")

# Shared-entry-point folders (wrapping the raw API here counts as a wrapper)
# lib only as src/lib (Flutter lib/ is the whole app); client is left out because it is a monorepo folder name
COMMON_DIRECTORY_NAMES = {"design", "design_system", "common", "core", "shared", "ui", "network", "http",
                          "apis", "api", "clients", "infrastructure", "infra", "utils", "support"}
# Direct raw API calls (fact version of the stack docs' "common AI smells") — (language set, name, pattern)
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
# With no shared entry point, this many files or more makes an extraction candidate (rule of three — conventions §1)
RULE_OF_THREE_FILES = 3

# Named constant definitions (only string or number literal values)
CONSTANT_DEFINITION_PATTERNS = {
    "java": re.compile(r"\bstatic\s+final\s+[\w<>]+\s+([A-Z][A-Z0-9_]+)\s*=\s*(\"[^\"]{3,}\"|-?\d[\d_.]*[LlFfDd]?)\s*;"),
    "kotlin": re.compile(r"\bconst\s+val\s+([A-Z][A-Z0-9_]+)\s*(?::\s*\w+)?\s*=\s*(\"[^\"]{3,}\"|-?\d[\d_.]*)"),
    "dart": re.compile(r"\bconst\s+(?:[\w<>]+\s+)?([a-zA-Z_]\w*)\s*=\s*('[^']{3,}'|\"[^\"]{3,}\"|-?\d[\d_.]*)\s*;"),
    "python": re.compile(r"^([A-Z][A-Z0-9_]+)\s*(?::\s*\w+)?\s*=\s*('[^']{3,}'|\"[^\"]{3,}\"|-?\d[\d_.]*)\s*(?:#.*)?$"),
    "javascript": re.compile(r"\bconst\s+([A-Z][A-Z0-9_]+)\s*(?::\s*\w+)?\s*=\s*('[^']{3,}'|\"[^\"]{3,}\"|`[^`$]{3,}`|-?\d[\d_.]*)\s*;?"),
}
CONSTANT_DEFINITION_PATTERNS["typescript"] = CONSTANT_DEFINITION_PATTERNS["javascript"]


def long_functions(text: str, language: str) -> list[dict]:
    """Functions and methods over 60 lines [{name, line, lines}] (approximated by brace matching / Python indentation)"""
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
    """(bypasses, extraction candidates) — files: [(relative path, language, code lines [(number, line)])]

    Bypass: the same raw call exists inside a shared folder (wrapper candidate) yet is also called directly outside it
    Extraction candidate: no wrapper and called directly from 3+ files
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
    """Same-value constants in 2+ files (config values and key names need a single source even at 2 places — conventions §1, §5)

    Strings are grouped by value, numbers by name+value (so common numbers like 0 and 1 with different names are not grouped)
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
