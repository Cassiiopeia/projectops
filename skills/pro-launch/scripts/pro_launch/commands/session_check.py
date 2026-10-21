"""`session-check` — 긴 작업을 마칠 때 한 번: 아직 실패 중인 영역 · 막혔다 풀렸는데 learn 하지 않은 영역 ·
pro-launch 밖에서 돈 Maestro 실행 (#863)."""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from common.state import repo_unknown

import knowledge
import maestro_runs

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root
from pro_launch.runtime.output import RESOLVED_FILE, out

ATTEMPTS_FILE = "attempts.json"
# 이 시간 안의 기록만 '이번 세션'으로 본다
SESSION_WINDOW_HOURS = 12
# 이 시간 안의 ~/.maestro/tests 폴더만 센다
OUTSIDE_LAUNCH_WINDOW_HOURS = 24


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
    # launch_cli 를 안 거친 Maestro 직접 실행 — 그 사이 알게 된 방식은 기억에 안 남는다 (adb 는 흔적이 없어 못 센다)
    outside_launch = {"maestro_runs": maestro_runs.count_outside_runs(OUTSIDE_LAUNCH_WINDOW_HOURS * 3600)}
    outside_count = outside_launch["maestro_runs"]
    if not still_failing and not unlearned and not outside_count:
        return out({"ok": True, "code": "ok", "still_failing": [], "unlearned": [], "outside_launch": outside_launch,
                    "summary": f"No lesson candidates to record in the last {SESSION_WINDOW_HOURS} hours", "next": None})
    areas = sorted({row["area"] for row in unlearned})
    return out({"ok": True, "code": "learn_candidates", "still_failing": still_failing, "unlearned": unlearned,
                "outside_launch": outside_launch,
                "summary": "Lesson candidates to record ("
                           + " · ".join(part for part in (
                               f"{len(unlearned)} area(s) not learned" if unlearned else "",
                               f"{len(still_failing)} still failing" if still_failing else "",
                               f"{outside_count} Maestro run(s) outside pro-launch ({OUTSIDE_LAUNCH_WINDOW_HOURS}h)"
                               if outside_count else "") if part) + ")",
                "next": _next_step(areas, outside_count)})


def _next_step(areas: list[str], outside_count: int) -> str:
    """learn 할 영역 > 직접 실행한 Maestro > 실패 중만 남음 순."""
    if areas:
        return (f"Record what worked with learn --area {areas[0]} --key <short-key> --how '<one-line conclusion>' --result ok "
                "--detail '<why it was blocked and how it was solved>'")
    if outside_count:
        return (f"Maestro ran {outside_count} time(s) directly outside pro-launch — if something worked there, "
                "record it with learn --area ios|android --key <short-key> --how '<one-line conclusion>' --result ok")
    return "Record still-failing areas once they are solved (do not record unsolved trial and error)"


def configure(p) -> None:
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="session-check",
            help="When finishing work: areas still failing · areas that got unblocked but were not learned",
            run=cmd_session_check, configure=configure),
]
