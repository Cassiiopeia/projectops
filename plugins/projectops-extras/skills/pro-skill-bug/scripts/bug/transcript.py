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
# 대화 행만 읽음 (api-request-blob 등은 같은 블록 사본)
CONVERSATION_ROW_TYPES = ("user", "assistant")
# 사용자 말이 아닌 주입 메시지 머리 (명령 · 알림 · 이미지 표식)
SYSTEM_MESSAGE_PREFIXES = ("<", "[Image")


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


def _is_user_words(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and not stripped.startswith(SYSTEM_MESSAGE_PREFIXES)


def iter_rows(path: Path) -> Iterator[dict]:
    """기록 줄 > 원본 행 (깨진 줄 · 대화 아닌 행 건너뜀, cwd 등 행 메타가 필요할 때)"""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("type") in CONVERSATION_ROW_TYPES:
                yield row


def iter_events(path: Path) -> Iterator[dict]:
    """기록 줄 > 정규화 이벤트 (user · assistant_text · tool_use · tool_result)
    건너뜀 5종: 깨진 줄, 대화 아닌 행, isMeta(스킬 본문 주입), 시스템 태그 메시지, 같은 id 사본"""
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
