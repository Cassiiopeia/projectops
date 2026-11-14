"""Where to put captures, their names · shrinking. app and web use the same rules."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from common.image import SHOT_MAX_SIDE, WEBP_QUALITY, to_webp

from pro_launch.runtime.context import state_home
from pro_launch.runtime.output import add_response_fields
from pro_launch.runtime.session_identity import session_identity

# Run folder record left by get-output-path: <state folder>/last_run.json {"sessions": {session: {run_dir, screenshots, at}}} (#931)
# Per-session records — so captures do not mix into the run folder of another session on the same repo (#972)
LAST_RUN_FILE = "last_run.json"
# Only records within this window are used — so today's captures do not land in a run folder from days ago (12 hours)
LAST_RUN_VALID_SECONDS = 12 * 60 * 60
# 3 capture-location sources: env (SHOT_DIR) · last_run (this session's latest get-output-path) · state (state folder shots)
SHOT_DIR_SOURCES = ("env", "last_run", "state")


def _read_last_runs(root: Path) -> dict:
    """{session: record}. The old shape without session keys (single entry) is dropped since its owner is unknown."""
    try:
        data = json.loads((state_home(root) / LAST_RUN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    sessions = data.get("sessions") if isinstance(data, dict) else None
    return {k: v for k, v in sessions.items() if isinstance(v, dict)} if isinstance(sessions, dict) else {}


def _is_recent_row(row: dict, now: float) -> bool:
    """Is the record within its valid window. Rows with a broken at count as expired (so get-output-path never dies)"""
    try:
        return now - float(row.get("at") or 0) < LAST_RUN_VALID_SECONDS
    except (TypeError, ValueError):
        return False


def record_last_run(root: Path, run_dir: Path, screenshots: Path) -> None:
    """Called by get-output-path — changes only this session's slot. A record failure does not block the command."""
    target = state_home(root) / LAST_RUN_FILE
    sessions = _read_last_runs(root)
    now = time.time()
    sessions = {k: v for k, v in sessions.items() if _is_recent_row(v, now)}
    sessions[session_identity()] = {"run_dir": str(run_dir), "screenshots": str(screenshots), "at": now}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"sessions": sessions}), encoding="utf-8")
    except OSError:
        pass


def _fresh_run(row: dict) -> Path | None:
    """screenshots folder of a valid record (within 12 hours · run folder still exists)."""
    try:
        is_fresh = time.time() - float(row.get("at") or 0) < LAST_RUN_VALID_SECONDS
        run_dir, screenshots = Path(row["run_dir"]), Path(row["screenshots"])
    except (ValueError, TypeError, KeyError):
        return None
    return screenshots if is_fresh and run_dir.is_dir() else None


def _last_run_screenshots(root: Path) -> Path | None:
    """screenshots folder of this session's latest run. If only other sessions' records exist, do not use them and attach a warning to the response."""
    sessions = _read_last_runs(root)
    own = sessions.get(session_identity())
    if own is not None and (folder := _fresh_run(own)) is not None:
        return folder
    if any(_fresh_run(row) is not None for name, row in sessions.items() if name != session_identity()):
        add_response_fields({"shot_dir_note": "The latest get-output-path run belongs to another session, so its folder was not used — "
                                              "call get-output-path in this session and source env.sh"})
    return None


def resolve_shot_folder(root: Path) -> tuple[Path, str]:
    """(capture location, source). Order: $SHOT_DIR > latest get-output-path run folder > state folder shots."""
    env_shot = os.environ.get("SHOT_DIR")
    if env_shot:
        return Path(env_shot), "env"
    last_run = _last_run_screenshots(root)
    if last_run is not None:
        return last_run, "last_run"
    return state_home(root) / "shots", "state"


def shot_dir_source(root: Path) -> str:
    """Capture location source > "env" | "last_run" | "state" — attached to results (tells whether env.sh was not sourced)."""
    return resolve_shot_folder(root)[1]


def shot_folder(root: Path) -> Path:
    """Where to put captures (the location from resolve_shot_folder). Created if missing."""
    d = resolve_shot_folder(root)[0]
    d.mkdir(parents=True, exist_ok=True)
    return d


def shot_target(root: Path, name: str | None, ext: str = ".png") -> tuple[Path, bool]:
    """(save path, was the path given directly). A bare name goes under SHOT_DIR."""
    if name and (os.sep in name or "/" in name):
        p = Path(name)
        # Add an extension if missing — browser capture fails with unsupported mime type (#972)
        if not p.suffix:
            p = p.with_name(p.name + ext)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p, True
    stem = Path(name).stem if name else time.strftime("%Y%m%d-%H%M%S")
    return shot_folder(root) / f"{stem}{ext}", False


def finish_shot(raw: Path, explicit: bool, args) -> Path:
    """Keep as is if the path was given directly or --keep-format; otherwise shrink and convert to WebP."""
    if explicit or getattr(args, "keep_format", False):
        return raw
    return to_webp(raw, quality=args.quality, max_side=args.max_side or None) or raw


def add_shot_args(p) -> None:
    # Session tokens shrink only with resolution. 0 keeps the original size.
    p.add_argument("--max-side", type=int, default=SHOT_MAX_SIDE,
                   help=f"Longest side limit (default {SHOT_MAX_SIDE}, 0 keeps the original)")
    p.add_argument("--quality", type=int, default=WEBP_QUALITY,
                   help=f"WebP quality (default {WEBP_QUALITY})")
    p.add_argument("--keep-format", action="store_true",
                   help="Keep the original PNG — when the original is needed, e.g. pixel comparison")
