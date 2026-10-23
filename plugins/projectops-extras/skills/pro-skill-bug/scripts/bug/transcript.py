"""Claude Code 세션 기록(jsonl) 찾기 · 줄 단위 정규화

기록 위치: <설정 폴더>/projects/<작업 경로의 / . 를 - 로>/<세션 ID>.jsonl
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

# 현재 세션 ID · 설정 폴더 환경변수 (Claude Code 가 넣는다)
SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"


def config_dirs() -> list[Path]:
    """찾을 설정 폴더: $CLAUDE_CONFIG_DIR > ~/.claude (중복 제거)"""
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
    """작업 경로 > 기록 폴더 이름 (/Users/a/b.c > -Users-a-b-c)"""
    return str(cwd).replace("/", "-").replace(".", "-")


def find_transcript(session_id: str | None, cwd: Path | None = None,
                    dirs: list[Path] | None = None) -> Path | None:
    """세션 기록 파일: 작업 경로 폴더 먼저 > 없으면 projects/* 전체에서 같은 ID"""
    session_id = session_id or os.environ.get(SESSION_ID_ENV) or ""
    if not session_id:
        return None
    cwd = cwd or Path.cwd()
    for base in dirs or config_dirs():
        direct = base / "projects" / project_slug(cwd) / f"{session_id}.jsonl"
        if direct.is_file():
            return direct
        # 세션 도중 작업 경로를 옮겼으면 다른 폴더에 있다
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


def iter_events(path: Path) -> Iterator[dict]:
    """기록 줄 > 정규화 이벤트 (user · assistant_text · tool_use · tool_result). 깨진 줄은 건너뜀"""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            content = (row.get("message") or {}).get("content")
            if isinstance(content, str):
                if row.get("type") == "user":
                    yield _event(index, "user", content)
                continue
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "tool_use":
                    yield _event(index, "tool_use", _tool_use_text(block), block.get("id"), block.get("name"))
                elif block_type == "tool_result":
                    yield _event(index, "tool_result", _tool_result_text(block.get("content")), block.get("tool_use_id"))
                elif block_type == "text" and row.get("type") == "assistant":
                    yield _event(index, "assistant_text", block.get("text", ""))
                elif block_type == "text" and row.get("type") == "user":
                    yield _event(index, "user", block.get("text", ""))
