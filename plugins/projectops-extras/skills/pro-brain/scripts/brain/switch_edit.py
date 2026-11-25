"""Repo switch writer: set keys inside version.yml metadata.template.options.knowledge, keeping every other line as is
Line-based (no YAML library in extras): only the knowledge block changes, comments and order elsewhere stay.
"""
from __future__ import annotations

import json
import re

OPTIONS_PATH = ("metadata", "template", "options")
DEFAULT_KNOWLEDGE_PATH = "knowledge/"


class SwitchEditError(Exception):
    pass


def format_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(str(item), ensure_ascii=False) for item in value) + "]"
    if isinstance(value, dict):
        # One-line flow map (team_brain), so the line-based writer never has to manage a nested block
        return "{ " + ", ".join(f"{key}: {json.dumps(str(item), ensure_ascii=False)}" for key, item in value.items()) + " }"
    return json.dumps(str(value), ensure_ascii=False)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_content(line: str) -> bool:
    return bool(line.strip()) and not line.lstrip().startswith("#")


def _block_end(lines: list[str], start: int, indent: int) -> int:
    """Index after the last content line deeper than indent (trailing blank and comment lines excluded)"""
    last = start
    for index in range(start + 1, len(lines)):
        if _is_content(lines[index]):
            if _indent(lines[index]) <= indent:
                break
            last = index
    return last + 1


def _find_child(lines: list[str], start: int, end: int, parent_indent: int, key: str) -> int | None:
    child_indent = None
    for index in range(start, end):
        line = lines[index]
        if not _is_content(line):
            continue
        if _indent(line) <= parent_indent:
            return None
        child_indent = child_indent if child_indent is not None else _indent(line)
        if _indent(line) == child_indent and re.match(rf"^\s*{re.escape(key)}:(\s|$)", line):
            return index
    return None


def _locate(lines: list[str], path: tuple[str, ...]) -> tuple[int, int] | None:
    """(line index, indent) of the last key in path, walking direct children only"""
    start, end, indent, found = 0, len(lines), -1, None
    for key in path:
        index = _find_child(lines, start, end, indent, key)
        if index is None:
            return None
        found, indent = index, _indent(lines[index])
        start, end = index + 1, _block_end(lines, index, indent)
    return found, indent


def _child_block_end(lines: list[str], index: int) -> int:
    """Index after a key line and its deeper lines (an indented map under the key)"""
    return max(index + 1, _block_end(lines, index, _indent(lines[index])))


def _ensure_options_block(lines: list[str]) -> None:
    """Add the missing metadata / template / options levels in place (sibling indent, other lines untouched)"""
    if not any(_is_content(line) for line in lines):
        raise SwitchEditError("version.yml is empty: install projectops first (npx projectops@latest --mode version)")
    start, end, indent = 0, len(lines), -1
    for key in OPTIONS_PATH:
        index = _find_child(lines, start, end, indent, key)
        if index is None:
            siblings = [line for line in lines[start:end] if _is_content(line) and _indent(line) > indent]
            child_indent = min((_indent(line) for line in siblings), default=indent + 2 if indent >= 0 else 0)
            # Appended at the end of the parent block (top level: end of file)
            lines.insert(end, " " * child_indent + f"{key}:")
            index = end
        indent = _indent(lines[index])
        if re.match(rf"^\s*{re.escape(key)}:\s*\S", lines[index]) and not lines[index].split(":", 1)[1].lstrip().startswith("#"):
            raise SwitchEditError(f"version.yml {key} is a one-line value: turn it into an indented block, then run again")
        start, end = index + 1, _block_end(lines, index, indent)


def set_knowledge_keys(text: str, updates: dict, create_if_missing: bool, removals: tuple[str, ...] = ()) -> str:
    """Set (or add) keys in the knowledge block; creates missing metadata.template.options levels and the block when asked"""
    lines = text.splitlines()
    options = _locate(lines, OPTIONS_PATH)
    if options is None:
        _ensure_options_block(lines)
        options = _locate(lines, OPTIONS_PATH)
    options_index, options_indent = options
    options_end = _block_end(lines, options_index, options_indent)
    knowledge_index = _find_child(lines, options_index + 1, options_end, options_indent, "knowledge")
    if knowledge_index is None:
        if not create_if_missing:
            raise SwitchEditError("knowledge block is missing (pass --enable to create it)")
        child_indent = " " * (options_indent + 2)
        new_block = [f"{child_indent}knowledge:                     # pro-brain knowledge capture (kept on updates)"]
        # No path line when repo notes are off (the reader defaults it anyway)
        values = {"enabled": True, **({} if "path" in removals else {"path": DEFAULT_KNOWLEDGE_PATH}), **updates}
        new_block += [f"{child_indent}  {key}: {format_value(value)}" for key, value in values.items()]
        lines[options_end:options_end] = new_block
        return "\n".join(lines) + "\n"
    if re.match(r"^\s*knowledge:\s*\{", lines[knowledge_index]):
        raise SwitchEditError("knowledge is a one-line { } map: turn it into an indented block, then run again")
    knowledge_indent = _indent(lines[knowledge_index])
    knowledge_end = _block_end(lines, knowledge_index, knowledge_indent)
    child_lines = [index for index in range(knowledge_index + 1, knowledge_end) if _is_content(lines[index])]
    child_indent = " " * (_indent(lines[child_lines[0]]) if child_lines else knowledge_indent + 2)
    for key in removals:
        existing = _find_child(lines, knowledge_index + 1, knowledge_end, knowledge_indent, key)
        if existing is not None:
            end = _child_block_end(lines, existing)
            del lines[existing:end]
            knowledge_end -= end - existing
    for key, value in updates.items():
        existing = _find_child(lines, knowledge_index + 1, knowledge_end, knowledge_indent, key)
        if existing is not None:
            comment = re.search(r"\s+#\s.*$", lines[existing])
            end = _child_block_end(lines, existing)
            # Replacing a key that had an indented map (team_brain) drops the old child lines too
            lines[existing:end] = [f"{child_indent}{key}: {format_value(value)}" + (comment.group(0) if comment else "")]
            knowledge_end -= end - existing - 1
        else:
            lines.insert(knowledge_end, f"{child_indent}{key}: {format_value(value)}")
            knowledge_end += 1
    return "\n".join(lines) + "\n"
