"""`web open` self-recovery: judge the recorded browser state (dead, hung, healthy) > clean leftover profile locks (#887).

After a crash or window close produced `browser_start_failed`, the agent checked pids, deleted locks and retried by hand.
This judges it in one go and returns what it cleaned as `recovered`. Only pids written in the state file (that we launched) are killed.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from pro_launch.commands.web.watchdog import HUNG_MARK_KEY
from pro_launch.runtime.procs import kill_browser, pid_alive, process_command_lines

# The 3 locks Chromium leaves in the profile (on macOS and Linux SingletonLock is a symlink pointing to "host-pid")
PROFILE_LOCK_NAMES = ("SingletonLock", "SingletonSocket", "SingletonCookie")
# If CDP doesn't answer within this time, treat the browser as hung (seconds)
HUNG_PROBE_SECONDS = 3.0
# Waiting long for a hung browser to exit cleanly is useless — wait briefly, then force kill (seconds)
HUNG_KILL_GRACE_SECONDS = 1.0
# Number of trailing browser stderr lines included in the failure response
STDERR_TAIL_LINES = 12
BROWSER_STDERR_FILE = "browser-stderr.log"


def profile_in_use(profile: Path) -> bool:
    """Is a browser process running with this profile. If it can't be checked, treat it as in use (never delete someone else's lock)."""
    command_lines = process_command_lines()
    if not command_lines:
        return True
    # Windows quotes paths with spaces, so search for the path itself, not the argument name
    return str(profile) in command_lines


def has_profile_lock(profile: Path) -> bool:
    # A symlink whose target is gone is still a lock — exists() follows the link and returns False
    return any(os.path.lexists(profile / name) for name in ("SingletonLock", "SingletonSocket"))


def clear_stale_locks(profile: Path) -> bool:
    """Delete locks only when no process uses the profile. True if anything was deleted."""
    if not any(os.path.lexists(profile / name) for name in PROFILE_LOCK_NAMES):
        return False
    if profile_in_use(profile):
        return False
    removed = False
    for name in PROFILE_LOCK_NAMES:
        try:
            (profile / name).unlink()
            removed = True
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            pass
    return removed


def cdp_responds(cdp: str, timeout: float = HUNG_PROBE_SECONDS) -> bool:
    """Does the CDP endpoint return version info within the time limit. A Playwright connection waits without limit on a hung browser."""
    try:
        with urllib.request.urlopen(f"{cdp.rstrip('/')}/json/version", timeout=timeout) as response:
            return "Browser" in json.loads(response.read().decode("utf-8", "replace"))
    except Exception:
        return False


def recover_recorded_browser(previous_state: dict, profile: Path) -> tuple[str, list[str]]:
    """Judge the recorded browser > ("reuse" | "launch" | "blocked", list of cleaned items).

    Alive and CDP answers > reuse; alive but no answer or hung mark (hung_at) > kill; dead > clean locks only.
    blocked: the hung browser could not be killed.
    """
    recovered: list[str] = []
    pid = previous_state.get("pid")
    cdp = previous_state.get("cdp")
    if pid and pid_alive(int(pid)):
        # hung_at: the last command hung while attaching or acting — even if CDP answers, reattaching would hang again (#921)
        if cdp and cdp_responds(cdp) and not previous_state.get(HUNG_MARK_KEY):
            return "reuse", recovered
        if kill_browser(int(pid), grace=HUNG_KILL_GRACE_SECONDS):
            return "blocked", recovered
        recovered.append("hung_browser")
    elif pid:
        recovered.append("dead_pid")
    if clear_stale_locks(profile):
        recovered.append("stale_lock")
    return "launch", recovered


def stderr_tail(log_path: Path, line_count: int = STDERR_TAIL_LINES) -> list[str] | None:
    """Last lines of the browser's stderr. None if empty."""
    try:
        lines = [line.rstrip() for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        return None
    lines = [line for line in lines if line]
    return lines[-line_count:] or None
