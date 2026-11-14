"""Hook session state > alarm evidence (#1000). Reads only the state file, does not import hook rules"""
from __future__ import annotations

import json
from pathlib import Path

from bug.redact import redact_text

# Hook session state: ~/.projectops/cache/pro-skill-bug/watch/{session_id}.json (same location as hooks/skill_bug_watch.py)
WATCH_FOLDER_PARTS = (".projectops", "cache", "pro-skill-bug", "watch")


def state_path(session_id: str) -> Path:
    return Path.home().joinpath(*WATCH_FOLDER_PARTS) / f"{session_id}.json"


def load_alarms(session_id: str) -> list[dict] | None:
    """State file > alarm list (None if missing or broken, empty list if no alarms)"""
    try:
        state = json.loads(state_path(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return list(state.get("alarms") or [])


def redact_alarm(alarm: dict) -> tuple[dict, dict]:
    """Redact alarm text fields (result head · workaround command) > (redacted alarms, count per kind)"""
    counts: dict = {}
    cleaned = dict(alarm)
    for field in ("excerpt", "workaround"):
        if isinstance(cleaned.get(field), str):
            cleaned[field], field_counts = redact_text(cleaned[field])
            for kind, hits in field_counts.items():
                counts[kind] = counts.get(kind, 0) + hits
    return cleaned, counts
