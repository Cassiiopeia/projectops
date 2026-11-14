"""`session-check` — run once when finishing long work: areas still failing · areas unblocked but not learned ·
Maestro runs outside pro-launch (#863)."""
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
# Only records within this window count as 'this session'
SESSION_WINDOW_HOURS = 12
# Only ~/.maestro/tests folders within this window are counted
OUTSIDE_LAUNCH_WINDOW_HOURS = 24


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _learned_dates(root: Path, is_unknown: bool) -> dict[str, str]:
    """Area > last-used date of that area's memory (latest of repo and machine scopes)."""
    scopes = ("machine",) if is_unknown else ("repo", "machine")
    summary = knowledge.area_summary({scope: knowledge.store_path(scope, root) for scope in scopes})
    return {area: row["last_seen"] for area, row in summary.items() if row["last_seen"]}


def cmd_session_check(args) -> int:
    root = project_root(args)
    is_unknown = repo_unknown(root)
    state_folder = knowledge.store_path("machine" if is_unknown else "repo", root).parent
    since = time.time() - SESSION_WINDOW_HOURS * 3600
    # Still failing: no success in the same area after the failure
    attempts = _read_json(state_folder / ATTEMPTS_FILE, {})
    still_failing = [{"area": area, "last_code": row.get("code"), "fails": row.get("fails", 1)}
                     for area, row in (attempts.items() if isinstance(attempts, dict) else [])
                     if isinstance(row, dict) and float(row.get("at") or 0) >= since]
    # Unblocked, but no learn for that area since
    learned = _learned_dates(root, is_unknown)
    resolved = _read_json(state_folder / RESOLVED_FILE, [])
    unlearned = []
    for row in resolved if isinstance(resolved, list) else []:
        at = float(row.get("at") or 0)
        resolved_day = dt.date.fromtimestamp(at).isoformat()
        if at >= since and (learned.get(row.get("area")) or "") < resolved_day:
            unlearned.append({"area": row.get("area"), "fails": row.get("fails"), "last_code": row.get("last_code")})
    # Maestro run directly, not via launch_cli — methods learned meanwhile are not remembered (adb leaves no trace, so it cannot be counted)
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
    """Order: areas to learn > Maestro run directly > only still-failing left."""
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
