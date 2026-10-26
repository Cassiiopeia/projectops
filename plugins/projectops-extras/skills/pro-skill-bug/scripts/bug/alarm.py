"""훅 세션 상태 > 경보 근거 (#1000). 훅 규칙은 import 하지 않고 상태 파일만 읽는다"""
from __future__ import annotations

import json
from pathlib import Path

from bug.redact import redact_text

# 훅 세션 상태: ~/.projectops/cache/pro-skill-bug/watch/{session_id}.json (hooks/skill_bug_watch.py 와 같은 위치)
WATCH_FOLDER_PARTS = (".projectops", "cache", "pro-skill-bug", "watch")


def state_path(session_id: str) -> Path:
    return Path.home().joinpath(*WATCH_FOLDER_PARTS) / f"{session_id}.json"


def load_alarms(session_id: str) -> list[dict] | None:
    """상태 파일 > 경보 목록 (파일 없거나 깨지면 None, 경보 없으면 빈 목록)"""
    try:
        state = json.loads(state_path(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return list(state.get("alarms") or [])


def redact_alarm(alarm: dict) -> tuple[dict, dict]:
    """경보의 글 칸(결과 머리 · 우회 명령) 가리기 > (가린 경보, 종류별 개수)"""
    counts: dict = {}
    cleaned = dict(alarm)
    for field in ("excerpt", "workaround"):
        if isinstance(cleaned.get(field), str):
            cleaned[field], field_counts = redact_text(cleaned[field])
            for kind, hits in field_counts.items():
                counts[kind] = counts.get(kind, 0) + hits
    return cleaned, counts
