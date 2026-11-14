"""Record of recently used project roots · finding candidates (#885).

Agent shells change the working folder every call. Called from outside a repo, the root was not found and git_not_found·browser_not_open followed.
Roots used by this skill are recorded in this computer's shared spot, and the latest one is used when the working folder is not a repo.

  ~/.projectops/launch/_machine/recent_roots.json   {"roots": [{"path", "at", "session"}]}  newest first
The fallback root for calls outside a repo is picked only from this session's — so it never attaches to another session's repo (and browser)
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from common.state import MACHINE_BUCKET, base_dir, is_scratch_root, launch_file

from pro_launch.runtime.procs import pid_alive
from pro_launch.runtime.session_identity import ANONYMOUS_SESSION, session_identity

RECENT_ROOTS_FILE = "recent_roots.json"
# Generous, since each session keeps its own entries (one shared file)
MAX_RECENT_ROOTS = 30
# Using the same root again within this interval does not rewrite the file (avoids a write per command)
REWRITE_INTERVAL_SECONDS = 600
BROWSER_STATE_FILE = "browser.json"


def recent_roots_path() -> Path:
    return base_dir() / "launch" / MACHINE_BUCKET / RECENT_ROOTS_FILE


def is_git_work_tree(path: Path) -> bool:
    """Is path inside a git work tree."""
    try:
        result = subprocess.run(["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def load_recent_roots() -> list[dict]:
    """[{path, at}] newest first. Folders that no longer exist are dropped. Empty list if unreadable."""
    try:
        data = json.loads(recent_roots_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("roots") if isinstance(data, dict) else None
    # Temp folders recorded earlier (jobs/tmp/formedit etc.) are excluded from candidates (#932)
    return [r for r in rows or [] if isinstance(r, dict) and r.get("path") and Path(r["path"]).is_dir()
            and not is_scratch_root(Path(r["path"]))]


def remember_root(root: Path) -> None:
    """Put the root used now first, per (root, session). A record failure does not block the command."""
    path_text = str(root)
    session = session_identity()
    rows = load_recent_roots()
    now = time.time()
    own = [r for r in rows if r.get("session", ANONYMOUS_SESSION) == session]
    if own and own[0]["path"] == path_text and now - float(own[0].get("at") or 0) < REWRITE_INTERVAL_SECONDS:
        return
    rows = [{"path": path_text, "at": now, "session": session}] + [
        r for r in rows if not (r["path"] == path_text and r.get("session", ANONYMOUS_SESSION) == session)]
    target = recent_roots_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps({"roots": rows[:MAX_RECENT_ROOTS]}), encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        pass


def last_used_root() -> Path | None:
    """Root this session used most recently. If the session is unknown (anonymous), the most recent across this computer"""
    session = session_identity()
    rows = load_recent_roots()
    if session != ANONYMOUS_SESSION:
        rows = [r for r in rows if r.get("session") == session]
    return Path(rows[0]["path"]) if rows else None


def has_live_browser(root: Path) -> bool:
    """Is a browser this skill launched for that repo alive (checked via the state file pid)."""
    try:
        state = json.loads(launch_file(root, BROWSER_STATE_FILE).read_text(encoding="utf-8"))
        return bool(state.get("cdp")) and bool(state.get("pid")) and pid_alive(int(state["pid"]))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def root_candidates() -> list[dict]:
    """Candidates to pass as --root when rerunning: recent roots + whether a browser is alive. Live ones first."""
    paths = list(dict.fromkeys(r["path"] for r in load_recent_roots()))  # per-session rows repeat the same path
    rows = [{"path": path, "has_live_browser": has_live_browser(Path(path))} for path in paths]
    return sorted(rows, key=lambda row: not row["has_live_browser"])
