"""`session-check` — 긴 작업을 마칠 때 한 번: 아직 실패 중인 영역 · 막혔다 풀렸는데 learn 하지 않은 영역 (#863)."""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from common.state import repo_unknown

import knowledge

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root
from pro_launch.runtime.output import RESOLVED_FILE, out

ATTEMPTS_FILE = "attempts.json"
# 이 시간 안의 기록만 '이번 세션'으로 본다
SESSION_WINDOW_HOURS = 12


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _learned_dates(root: Path, is_unknown: bool) -> dict[str, str]:
    """영역 > 그 영역 기억의 마지막 사용일 (repo·machine 범위 중 최신)."""
    scopes = ("machine",) if is_unknown else ("repo", "machine")
    summary = knowledge.area_summary({scope: knowledge.store_path(scope, root) for scope in scopes})
    return {area: row["last_seen"] for area, row in summary.items() if row["last_seen"]}


def cmd_session_check(args) -> int:
    root = project_root(args)
    is_unknown = repo_unknown(root)
    state_folder = knowledge.store_path("machine" if is_unknown else "repo", root).parent
    since = time.time() - SESSION_WINDOW_HOURS * 3600
    # 아직 실패 중: 실패 뒤 같은 영역 성공이 없었다
    attempts = _read_json(state_folder / ATTEMPTS_FILE, {})
    still_failing = [{"area": area, "last_code": row.get("code"), "fails": row.get("fails", 1)}
                     for area, row in (attempts.items() if isinstance(attempts, dict) else [])
                     if isinstance(row, dict) and float(row.get("at") or 0) >= since]
    # 풀렸는데 그 뒤로 그 영역 learn 이 없다
    learned = _learned_dates(root, is_unknown)
    resolved = _read_json(state_folder / RESOLVED_FILE, [])
    unlearned = []
    for row in resolved if isinstance(resolved, list) else []:
        at = float(row.get("at") or 0)
        resolved_day = dt.date.fromtimestamp(at).isoformat()
        if at >= since and (learned.get(row.get("area")) or "") < resolved_day:
            unlearned.append({"area": row.get("area"), "fails": row.get("fails"), "last_code": row.get("last_code")})
    if not still_failing and not unlearned:
        return out({"ok": True, "code": "ok", "still_failing": [], "unlearned": [],
                    "summary": f"최근 {SESSION_WINDOW_HOURS}시간 동안 남길 교훈 후보가 없다", "next": None})
    areas = sorted({row["area"] for row in unlearned})
    return out({"ok": True, "code": "learn_candidates", "still_failing": still_failing, "unlearned": unlearned,
                "summary": (f"막혔다 풀린 영역 {len(unlearned)}건이 아직 learn 되지 않았다"
                            + (f" · 아직 실패 중 {len(still_failing)}건" if still_failing else "")),
                "next": (f"먹힌 방식을 learn --area {areas[0]} --key <짧은키> --how '<한 줄 결론>' --result ok "
                         "--detail '<왜 막혔고 어떻게 풀었나>' 로 남긴다" if areas
                         else "실패 중인 영역은 해결된 뒤에 남긴다 (해결 안 된 시행착오는 남기지 않는다)")})


def configure(p) -> None:
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="session-check",
            help="작업을 마칠 때: 아직 실패 중인 영역 · 막혔다 풀렸는데 learn 안 한 영역",
            run=cmd_session_check, configure=configure),
]
