"""Repo facts: git calls and version.yml reading (knowledge switch, version, build number, stack paths, branches)
Standard library only; version.yml is read with a small indentation parser because extras cannot rely on PyYAML.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# version.yml location of the repo switch: metadata > template > options > knowledge
KNOWLEDGE_BLOCK_PATH = ("metadata", "template", "options", "knowledge")
# Keys pro-brain reads from the switch; anything else in the block is kept by the installer and ignored here
KNOWLEDGE_KEYS = ("enabled", "path", "note_dir", "template", "rules", "check")


class GitError(Exception):
    pass


def run_git(repo_root: Path, *arguments: str) -> str:
    """git command > stdout text (utf-8 with replacement so non-ASCII output never crashes on Windows)"""
    completed = subprocess.run(["git", "-C", str(repo_root), *arguments], capture_output=True,
                               encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise GitError((completed.stderr or completed.stdout or "").strip() or f"git {' '.join(arguments)} failed")
    return completed.stdout


def find_repo_root(start: Path) -> Path | None:
    try:
        return Path(run_git(start, "rev-parse", "--show-toplevel").strip())
    except (GitError, FileNotFoundError):
        return None


def read_remote_slug(repo_root: Path) -> str | None:
    """origin URL > "owner/name" (https, ssh and .git forms)"""
    try:
        url = run_git(repo_root, "remote", "get-url", "origin").strip()
    except GitError:
        return None
    match = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    return f"{match.group(1)}/{match.group(2)}" if match else None


def current_branch(repo_root: Path) -> str | None:
    try:
        name = run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    except GitError:
        return None
    return None if name == "HEAD" else name


def read_version_yml_text(repo_root: Path, ref: str | None = None) -> str:
    """version.yml at a commit (ref) or in the working tree; empty text when missing"""
    if ref:
        try:
            return run_git(repo_root, "show", f"{ref}:version.yml")
        except GitError:
            pass
    path = repo_root / "version.yml"
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _strip_comment(value: str) -> str:
    """Drop a trailing ' # comment' outside quotes"""
    quote = None
    for index, character in enumerate(value):
        if quote:
            if character == quote:
                quote = None
        elif character in "\"'":
            quote = character
        elif character == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def _to_scalar(raw: str):
    value = _strip_comment(raw).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    lowered = value.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value or None


def _parse_flow_map(body: str) -> dict:
    """'a: 1, b: "x"' > {a: 1, b: "x"} (flat only; commas inside quotes are kept)"""
    items, current, quote = [], "", None
    for character in body:
        if quote:
            quote = None if character == quote else quote
        elif character in "\"'":
            quote = character
        elif character == ",":
            items.append(current)
            current = ""
            continue
        current += character
    items.append(current)
    result = {}
    for item in items:
        key, separator, value = item.partition(":")
        if separator and key.strip():
            result[key.strip()] = _to_scalar(value)
    return result


def read_nested_block(text: str, path: tuple[str, ...]) -> dict | None:
    """Indentation walk: path of keys > flat {key: scalar} of the last block's direct children (None when absent)"""
    lines = text.splitlines()
    start, indent = 0, -1
    for key in path:
        found = None
        direct_child_indent = None
        for index in range(start, len(lines)):
            line = lines[index]
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            line_indent = len(line) - len(line.lstrip(" "))
            if line_indent <= indent:
                break   # left the parent block
            direct_child_indent = line_indent if direct_child_indent is None else direct_child_indent
            # Only direct children match, so a deeper key with the same name is never taken
            if line_indent == direct_child_indent and re.match(rf"^\s*{re.escape(key)}:\s*(#.*)?$", line):
                found = (index, line_indent)
                break
            # One-line flow map on the last key: knowledge: { enabled: true, path: "knowledge/" }
            flow = re.match(rf"^\s*{re.escape(key)}:\s*\{{(.*)\}}\s*(#.*)?$", line)
            if line_indent == direct_child_indent and flow and key == path[-1]:
                return _parse_flow_map(flow.group(1))
        if not found:
            return None
        start, indent = found[0] + 1, found[1]
    children: dict = {}
    child_indent = None
    for line in lines[start:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        line_indent = len(line) - len(line.lstrip(" "))
        if line_indent <= indent:
            break
        child_indent = child_indent if child_indent is not None else line_indent
        match = re.match(r"^\s*([A-Za-z_][\w-]*):(.*)$", line)
        if line_indent == child_indent and match:
            children[match.group(1)] = _to_scalar(match.group(2))
    return children


def read_knowledge_switch(text: str) -> dict:
    """Repo switch > {present, enabled, path, note_dir, template, rules, check}; absent block = off"""
    block = read_nested_block(text, KNOWLEDGE_BLOCK_PATH)
    if block is None:
        return {"present": False, "enabled": False}
    switch = {key: block.get(key) for key in KNOWLEDGE_KEYS if block.get(key) is not None}
    switch["present"] = True
    switch["enabled"] = block.get("enabled") is True
    switch.setdefault("path", "knowledge/")
    return switch


def read_version_facts(text: str) -> dict:
    """version, version_code, project_types, project_paths and branch names from version.yml text"""
    def top(key):
        match = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE)
        return _to_scalar(match.group(1)) if match else None

    types_match = re.search(r"^project_types:\s*\[(.*?)\]", text, re.MULTILINE)
    project_types = re.findall(r"[\"']?([\w-]+)[\"']?", types_match.group(1)) if types_match else []
    project_paths = read_nested_block(text, ("project_paths",)) or {}
    metadata = read_nested_block(text, ("metadata",)) or {}
    return {
        "version": top("version"),
        "version_code": top("version_code"),
        "project_types": project_types,
        "project_paths": {key: str(value) for key, value in project_paths.items() if value is not None},
        # development_branch first, then the legacy deploy_branch, then develop (same order as the other skills)
        "development_branch": metadata.get("development_branch") or metadata.get("deploy_branch") or None,
        "default_branch": metadata.get("default_branch") or None,
    }
