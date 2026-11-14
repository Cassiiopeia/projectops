"""Generation history: one line per entry in harness history.jsonl (prompt, references, result, approval) > basis for the next request"""
from __future__ import annotations

import json
import time
from pathlib import Path

# Record status: approved user approved and used in the app, rejected user rejected, candidate generated only
STATUSES = ("approved", "rejected", "candidate")
# Prompt storage limit (characters)
PROMPT_KEEP_CHARACTERS = 6000


def append(history_path: Path, entry: dict) -> dict:
    record = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}
    if isinstance(record.get("prompt"), str):
        record["prompt"] = record["prompt"][:PROMPT_KEEP_CHARACTERS]
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read(history_path: Path, kind: str | None, status: str | None, limit: int) -> list[dict]:
    """Recent entries > filtered by kind and status, newest first, limit entries"""
    if not history_path.is_file():
        return []
    rows = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if (kind and row.get("kind") != kind) or (status and row.get("status") != status):
            continue
        rows.append(row)
    return list(reversed(rows))[:limit]
