"""diff: 변경분만 검사 > 낡은 주석 의심, 새 주석 문제, 기존 주석 고쳐 쓰기, 새 정의의 재사용 후보, 새 이름 문제

비교 대상: --base 커밋 <-> 작업 트리 (스테이징·미스테이징·추적 안 된 새 파일 포함)
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import code_smells
from .source_files import (classify_lines, comment_blocks, is_generated_file, iter_source_files,
                           language_of, split_identifier_words)

HUNK_HEADER_PATTERN = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
# 정의 줄 (함수·메서드·클래스) — 언어별, 이름은 첫 번째 잡힌 그룹
DEFINITION_PATTERNS = {
    "python": re.compile(r"^\s*(?:async\s+)?def\s+(\w+)|^\s*class\s+(\w+)"),
    "javascript": re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)"
        r"|^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>"
        r"|^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)"),
    "slash_typed": re.compile(
        r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|private|protected|static|final|abstract|override|async|"
        r"sealed|base|external|factory|synchronized|default)\s+)*(?:class|enum|interface|mixin|record)\s+(\w+)"
        r"|^\s*(?:(?:public|private|protected|static|final|abstract|override|synchronized|default)\s+)*"
        r"(?!(?:if|for|while|switch|return|catch|new|else|throw|await|super|this)\b)[\w<>\[\],?.]+\s+(\w+)\s*\([^;]*$"),
}
DEFINITION_PATTERNS["typescript"] = DEFINITION_PATTERNS["javascript"]
for _language in ("dart", "java", "kotlin"):
    DEFINITION_PATTERNS[_language] = DEFINITION_PATTERNS["slash_typed"]
# 낡은 주석 탐색: 변경 줄 바로 위 이 줄 수 안의 주석 블록
STALE_COMMENT_LOOKBACK_LINES = 3
# 재사용 후보: 이름 단어 겹침 비율 (Jaccard) 이 이상, 후보 최대 3개
REUSE_SIMILARITY_THRESHOLD = 0.5
REUSE_CANDIDATE_LIMIT = 3


def review_diff(root: Path, base: str, limit: int) -> dict:
    changed = _changed_files(root, base)
    if changed is None:
        return {"ok": False, "code": "git_failed", "summary": f"git diff 실패 (base={base})",
                "next": "git 레포인지, --base 가 있는 커밋인지 확인한다"}
    report = {key: [] for key in ("stale_comment_suspects", "added_comment_problems", "rewritten_existing_comments",
                                  "new_definitions", "new_boolean_names", "new_naming_problems")}
    definition_index = None

    for relative, added_lines, removed_texts in changed:
        language = language_of(relative)
        absolute = root / relative
        if not language or is_generated_file(relative) or not absolute.exists():
            continue
        text = absolute.read_text(encoding="utf-8", errors="replace")
        classified = classify_lines(text, language)
        comment_line_numbers = {n for n, kind, _ in classified if kind == "comment"}
        changed_code = sorted(n for n in added_lines if n not in comment_line_numbers)
        lines = text.splitlines()

        # 낡은 주석·고쳐 쓴 주석은 기존 파일만 (새 파일은 모든 줄이 추가라 의미 없음)
        is_new_file = not removed_texts and len(added_lines) >= len(lines)
        if not is_new_file:
            report["stale_comment_suspects"] += _stale_comments(relative, classified, added_lines, changed_code, language, lines)
            report["rewritten_existing_comments"] += _rewritten_comments(relative, classified, added_lines, removed_texts, changed_code)
        report["added_comment_problems"] += _added_comment_problems(relative, classified, added_lines)

        # 새 정의 > 재사용 후보 (색인은 처음 필요할 때 한 번만)
        removed_names = {_definition_name(t, language) for t in removed_texts} - {None}
        for number in added_lines:
            name = _definition_name(lines[number - 1], language)
            if not name or name in removed_names:
                continue
            if definition_index is None:
                definition_index = _definition_index(root)
            report["new_definitions"].append({"path": relative, "line": number, "name": name,
                                              "similar_existing": _similar(name, relative, definition_index)})
        for number in changed_code:
            line = lines[number - 1]
            for name in code_smells.boolean_names_in_line(line, language):
                report["new_boolean_names"].append({"path": relative, "line": number, "name": name})
            for kind, name, word in code_smells.naming_findings_in_line(line):
                report["new_naming_problems"].append({"path": relative, "line": number, "kind": kind, "name": name, "word": word})

    counts = {key: len(items) for key, items in report.items()}
    return {"base": base, "files_changed": len(changed), "counts": counts,
            **{key: items[:limit] for key, items in report.items()},
            "summary": f"변경 파일 {len(changed)}: 낡은 주석 의심 {counts['stale_comment_suspects']}, "
                       f"새 주석 문제 {counts['added_comment_problems']}, 기존 주석 고쳐 씀 {counts['rewritten_existing_comments']}, "
                       f"새 정의 {counts['new_definitions']}"}


def _changed_files(root: Path, base: str):
    """[(상대경로, 추가된 새 줄 번호 집합, 삭제된 줄 원문 목록)] — 실패 시 None"""
    try:
        diff = subprocess.run(["git", "-C", str(root), "diff", "--no-color", "--relative", "--unified=0", base, "--", "."],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
        untracked = subprocess.run(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    files, current, new_line = [], None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            current = None if path == "/dev/null" else (path[2:] if path.startswith("b/") else path, set(), [])
            if current:
                files.append(current)
        elif raw.startswith("@@") and current:
            match = HUNK_HEADER_PATTERN.match(raw)
            new_line = int(match.group(2)) if match else 0
        elif current and raw.startswith("+") and not raw.startswith("+++"):
            current[1].add(new_line)
            new_line += 1
        elif current and raw.startswith("-") and not raw.startswith("---"):
            current[2].append(raw[1:])
    for path in untracked.splitlines():
        absolute = root / path
        if absolute.is_file() and language_of(path):
            line_count = len(absolute.read_text(encoding="utf-8", errors="replace").splitlines())
            files.append((path, set(range(1, line_count + 1)), []))
    return files


def _stale_comments(relative, classified, added_lines, changed_code, language, lines):
    """바뀐 코드 바로 위 주석 블록, 바뀐 본문을 감싼 정의의 문서 주석 — 둘 다 그대로면 의심"""
    suspects, reported = [], set()
    blocks = [(start, length, content) for start, length, content in comment_blocks(classified)]
    block_ending_at = {start + length - 1: (start, length, content) for start, length, content in blocks}
    for number in changed_code:
        for distance in range(1, STALE_COMMENT_LOOKBACK_LINES + 1):
            block = block_ending_at.get(number - distance)
            if block:
                _add_suspect(suspects, reported, relative, block, added_lines, number, "comment_above_changed_code")
                break
            if number - distance in changed_code:
                break
        definition_line = _enclosing_definition(lines, number, language)
        if definition_line and definition_line not in added_lines:
            block = block_ending_at.get(definition_line - 1)
            if block:
                _add_suspect(suspects, reported, relative, block, added_lines, number, "doc_of_changed_definition")
    return suspects


def _add_suspect(suspects, reported, relative, block, added_lines, changed_line, reason):
    start, length, content = block
    if start in reported or any(n in added_lines for n in range(start, start + length)):
        return
    reported.add(start)
    suspects.append({"path": relative, "comment_line": start, "comment_length": length, "changed_line": changed_line,
                     "reason": reason, "comment": " / ".join(content)[:200]})


def _enclosing_definition(lines, number, language) -> int | None:
    pattern = DEFINITION_PATTERNS.get(language)
    for candidate in range(number - 1, 0, -1):
        if pattern and pattern.match(lines[candidate - 1]):
            return candidate
    return None


def _added_comment_problems(relative, classified, added_lines):
    problems = []
    for start, length, content in comment_blocks(classified):
        added = [n for n in range(start, start + length) if n in added_lines]
        if not added:
            continue
        kinds = sorted({k for text in content for k in code_smells.comment_phrase_findings(text)})
        if length >= code_smells.LONG_COMMENT_BLOCK_LINES:
            kinds.append("long_block")
        if kinds:
            problems.append({"path": relative, "line": start, "length": length, "kinds": kinds, "comment": " / ".join(content)[:200]})
    return problems


def _rewritten_comments(relative, classified, added_lines, removed_texts, changed_code):
    """주석만 바뀌고 주변 코드는 그대로인 블록 (건드리지 않은 코드의 주석을 고쳐 쓰지 않는다 — §7.6)"""
    removed_comments = [t.strip() for t in removed_texts if t.strip().startswith(("//", "#", "/*", "*", '"""'))]
    if not removed_comments:
        return []
    rewritten = []
    for start, length, content in comment_blocks(classified):
        block_lines = range(start, start + length)
        if not any(n in added_lines for n in block_lines):
            continue
        # 주석 블록 바로 위·아래 줄의 코드가 바뀌었으면 그 코드에 딸린 주석 수정 (정상)
        if any(start - 1 <= n <= start + length for n in changed_code):
            continue
        rewritten.append({"path": relative, "line": start, "comment": " / ".join(content)[:200]})
    return rewritten


def _definition_name(line: str, language: str) -> str | None:
    pattern = DEFINITION_PATTERNS.get(language)
    match = pattern.match(line) if pattern else None
    return next((g for g in match.groups() if g), None) if match else None


def _definition_index(root: Path) -> list[tuple[str, str, int]]:
    index = []
    for relative, language, text in iter_source_files(root):
        for number, line in enumerate(text.splitlines(), start=1):
            name = _definition_name(line, language)
            if name and len(name) > 2:
                index.append((name, relative, number))
    return index


def _similar(name: str, own_path: str, index) -> list[dict]:
    words = set(split_identifier_words(name))
    if not words:
        return []
    scored = []
    for other, path, number in index:
        if path == own_path and other == name:
            continue
        other_words = set(split_identifier_words(other))
        overlap = len(words & other_words) / len(words | other_words)
        if other == name or (overlap >= REUSE_SIMILARITY_THRESHOLD and len(words & other_words) >= 2):
            scored.append((overlap, {"name": other, "path": path, "line": number}))
    scored.sort(key=lambda item: -item[0])
    return [item for _, item in scored[:REUSE_CANDIDATE_LIMIT]]
