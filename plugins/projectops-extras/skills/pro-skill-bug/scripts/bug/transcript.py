"""Find Claude Code session transcripts (jsonl) · normalize line by line

Location: <config dir>/projects/<working path with / and . turned into ->/<session ID>.jsonl
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

# Current session ID · config dir env vars (set by Claude Code)
SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
# Read conversation rows only (api-request-blob etc. are copies of the same blocks)
CONVERSATION_ROW_TYPES = ("user", "assistant")
# Heads of injected messages that are not user text (commands · notifications · image markers)
SYSTEM_MESSAGE_PREFIXES = ("<", "[Image")


def config_dirs() -> list[Path]:
    """Config dirs to search: $CLAUDE_CONFIG_DIR > ~/.claude (deduplicated)"""
    candidates = []
    if os.environ.get(CONFIG_DIR_ENV):
        candidates.append(Path(os.environ[CONFIG_DIR_ENV]).expanduser())
    candidates.append(Path.home() / ".claude")
    unique = []
    for path in candidates:
        if path not in unique:
            unique.append(path)
    return unique


def project_slug(cwd: Path) -> str:
    """Working path > transcript folder name (/Users/a/b.c > -Users-a-b-c)"""
    return str(cwd).replace("/", "-").replace(".", "-")


def find_transcript(session_id: str | None, cwd: Path | None = None,
                    dirs: list[Path] | None = None) -> Path | None:
    """Session transcript file: working-path folder first > else the same ID anywhere under projects/*"""
    session_id = session_id or os.environ.get(SESSION_ID_ENV) or ""
    if not session_id:
        return None
    cwd = cwd or Path.cwd()
    for base in dirs or config_dirs():
        direct = base / "projects" / project_slug(cwd) / f"{session_id}.jsonl"
        if direct.is_file():
            return direct
        # If the working path moved mid-session, it lives in another folder
        matches = sorted((base / "projects").glob(f"*/{session_id}.jsonl"))
        if matches:
            return matches[0]
    return None


def _tool_use_text(block: dict) -> str:
    tool_input = block.get("input") or {}
    if block.get("name") == "Skill":
        return str(tool_input.get("skill", ""))
    if isinstance(tool_input.get("command"), str):
        return tool_input["command"]
    return json.dumps(tool_input, ensure_ascii=False)


def _tool_result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content
                         if isinstance(part, dict) and part.get("type") == "text")
    return ""


def _event(index: int, kind: str, text: str, tool_use_id=None, tool_name=None) -> dict:
    return {"index": index, "kind": kind, "text": text, "tool_use_id": tool_use_id, "tool_name": tool_name}


def _is_user_words(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and not stripped.startswith(SYSTEM_MESSAGE_PREFIXES)


def iter_rows(path: Path) -> Iterator[dict]:
    """Transcript lines > raw rows (skips broken and non-conversation rows; for when row metadata like cwd is needed)"""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("type") in CONVERSATION_ROW_TYPES:
                yield row


def iter_events(path: Path) -> Iterator[dict]:
    """Transcript lines > normalized events (user · assistant_text · tool_use · tool_result)
    5 kinds skipped: broken lines, non-conversation rows, isMeta (injected skill body), system-tag messages, same-id copies"""
    seen_block_ids: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or row.get("type") not in CONVERSATION_ROW_TYPES or row.get("isMeta"):
                continue
            content = (row.get("message") or {}).get("content")
            if isinstance(content, str):
                if row.get("type") == "user" and _is_user_words(content):
                    yield _event(index, "user", content)
                continue
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                block_id = block.get("id") or block.get("tool_use_id")
                if block_type in ("tool_use", "tool_result") and block_id:
                    if (block_type, block_id) in seen_block_ids:
                        continue
                    seen_block_ids.add((block_type, block_id))
                if block_type == "tool_use":
                    yield _event(index, "tool_use", _tool_use_text(block), block.get("id"), block.get("name"))
                elif block_type == "tool_result":
                    yield _event(index, "tool_result", _tool_result_text(block.get("content")), block.get("tool_use_id"))
                elif block_type == "text" and row.get("type") == "assistant":
                    yield _event(index, "assistant_text", block.get("text", ""))
                elif block_type == "text" and row.get("type") == "user" and _is_user_words(block.get("text", "")):
                    yield _event(index, "user", block.get("text", ""))
