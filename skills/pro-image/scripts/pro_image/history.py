"""생성 기록: 하네스 history.jsonl 에 한 줄씩 (프롬프트·참조·결과·승인 여부) > 다음 요청의 근거"""
from __future__ import annotations

import json
import time
from pathlib import Path

# 기록 상태: approved 사용자 승인·앱 반영, rejected 사용자 거절, candidate 생성만 됨
STATUSES = ("approved", "rejected", "candidate")
# 프롬프트 저장 한도 (글자)
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
    """최근 기록 > 종류·상태로 거른 뒤 최신순 limit 건"""
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
