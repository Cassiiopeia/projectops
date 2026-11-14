"""Pre-dispatch check: whether a workflow's actions/checkout ignores --ref with a fixed ref (#1185)."""
from __future__ import annotations

import base64
import re
import urllib.parse

_CHECKOUT_USES_PATTERN = re.compile(r"^\s*(?:-\s+)?uses:\s*['\"]?actions/checkout@")
_STEP_START_PATTERN = re.compile(r"^(\s*)-\s")
_REF_PATTERN = re.compile(r"^\s*ref:\s*(.+?)\s*(?:#.*)?$")
# A checkout of another repo has nothing to do with --ref
_REPOSITORY_PATTERN = re.compile(r"^\s*repository:\s*\S")


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _step_range(lines: list[str], uses_index: int) -> range:
    """Line range of the step a uses line belongs to (from the step's '- ' to the next item at the same indent)"""
    uses_indent = _indent_of(lines[uses_index])
    start = uses_index
    for index in range(uses_index, -1, -1):
        match = _STEP_START_PATTERN.match(lines[index])
        if match and len(match.group(1)) <= uses_indent:
            start = index
            break
    step_indent = _indent_of(lines[start])
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or _indent_of(lines[end]) > step_indent):
        end += 1
    return range(start, end)


def find_fixed_checkout_refs(workflow_text: str, dispatched_ref: str) -> list[dict]:
    """checkout steps whose fixed ref (not an expression) differs from dispatched_ref > [{line, ref}]"""
    lines = workflow_text.splitlines()
    wanted = dispatched_ref.removeprefix("refs/heads/").removeprefix("refs/tags/")
    mismatches = []
    for index, line in enumerate(lines):
        if not _CHECKOUT_USES_PATTERN.match(line):
            continue
        step = _step_range(lines, index)
        if any(_REPOSITORY_PATTERN.match(lines[step_index]) for step_index in step):
            continue
        for step_index in step:
            match = _REF_PATTERN.match(lines[step_index])
            if not match:
                continue
            fixed_ref = match.group(1).strip("'\"")
            if "${{" in fixed_ref:
                continue
            if fixed_ref.removeprefix("refs/heads/").removeprefix("refs/tags/") != wanted:
                mismatches.append({"line": step_index + 1, "ref": fixed_ref})
    return mismatches


def check_dispatch_ref(api, owner: str, repo: str, workflow: str, ref: str, pat: str) -> list[dict] | None:
    """Read the workflow file at --ref > fixed checkout refs. None if not a file name or unreadable"""
    if not workflow.endswith((".yml", ".yaml")):
        return None
    path = urllib.parse.quote(f".github/workflows/{workflow}")
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={urllib.parse.quote(ref, safe='')}"
    try:
        content = api._request("GET", url, None, pat)
        text = base64.b64decode(content.get("content", "")).decode("utf-8", "replace")
    except Exception:  # the check is an aid: failing to read never blocks dispatch
        return None
    return find_fixed_checkout_refs(text, ref)
