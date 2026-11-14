"""Browser state file · Playwright readiness · which browser to launch. Shared by web and doctor."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from common.state import base_dir, launch_file, venv_dir, venv_python, venv_site_packages

import browser_pick

from pro_launch.runtime.context import state_home
from pro_launch.runtime.procs import pid_alive, process_table


# Considered "abandoned" this long after last use — grounds for telling whether another session is using it (#825)
_STALE_BROWSER_HOURS = 6


def idle_hours(state: dict) -> float | None:
    """Time since last use (or open time if none). None if no record or unreadable."""
    used = state.get("last_used") or state.get("opened_at")
    try:
        return round((time.time() - time.mktime(time.strptime(used, "%Y-%m-%d %H:%M:%S"))) / 3600, 1)
    except (TypeError, ValueError):
        return None


def open_browser_status(state_f: Path) -> dict | None:
    """Is a browser running for this repo, and when was it last used. None if none."""
    st = read_state(state_f) if state_f.is_file() else {}
    pid = st.get("pid")
    if not pid:
        return None
    alive = pid_alive(int(pid))
    used = st.get("last_used") or st.get("opened_at")
    idle_h = idle_hours(st)
    stale = alive and idle_h is not None and idle_h >= _STALE_BROWSER_HOURS
    return {"pid": pid, "alive": alive, "opened_at": st.get("opened_at"), "last_used": used,
            "idle_hours": idle_h, "readonly": bool(st.get("readonly")), "stale": stale,
            "hint": (f"Browser idle for {idle_h} hours — unless another session is using it, clean up with web close or reattach with web open"
                     if stale else None)}


#
# The agent looks at screenshots to decide the next move, so actions are split across many CLI calls.
# Solved with **CDP reconnect** instead of a resident daemon:
#   open  → launch with --remote-debugging-port and write the port to the state file
#   after → connect_over_cdp attaches to that browser and detaches (session·cookies kept)
#
# ⚠️ Some things live only while attached — console hooks · viewport · response overrides. They vanish
# when the connection drops (observed in #625). So they are written to the state file and **reapplied on every attach.**
# Browser state file name — shared by the repo bucket · shared profile folder (#956)
WEB_STATE_FILE_NAME = "browser.json"
_WEB_STATE = WEB_STATE_FILE_NAME


def state_path(root: Path) -> Path:
    state_home(root)
    return launch_file(root, _WEB_STATE)


def read_state(f: Path) -> dict:
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(f: Path, state: dict) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def update_state_for_browser(f: Path, expected_pid, change) -> bool:
    """Re-read the state file > apply change only if it still points to expected_pid > written or not.

    A command reads the state, then spends seconds attaching or acting. Meanwhile another session can relaunch
    the browser on the same profile; writing the old copy back wiped the new pid and orphaned it (#1154).
    """
    fresh = read_state(f) if f.is_file() else {}
    if str(fresh.get("pid")) != str(expected_pid):
        return False
    change(fresh)
    write_state(f, fresh)
    return True


def require_playwright() -> tuple[object | None, dict | None]:
    """Load Playwright. Checks the dedicated venv → system, in that order.

    Imported inside the function because this script must not die entirely in projects
    that do not use the web. Apps and servers must run without Playwright.
    """
    sp = venv_site_packages()
    if sp and str(sp) not in sys.path:
        sys.path.insert(0, str(sp))
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright, None
    except ImportError:
        vd = venv_dir()
        return None, {
            "ok": False, "code": "playwright_missing",
            "error": "Playwright is required to open the web",
            "fix": "web setup  # creates a dedicated environment and downloads the browser (about 100MB)",
            "manual": f"{sys.executable} -m venv {vd} && "
                      f"{vd}/bin/pip install playwright pillow && "
                      f"{vd}/bin/python -m playwright install chromium",
            "why": ("Playwright is used directly to avoid depending on separate installs. "
                    "It goes into a dedicated environment so the system Python is untouched"),
            "ask_user": "Opening the web needs a browser download (about 100MB). Install it?",
        }


def bundled_chromium_path() -> str | None:
    """Where Playwright's bundled Chromium should be. None if Playwright is missing or unreadable."""
    sync_playwright, err = require_playwright()
    if err:
        return None
    try:
        with sync_playwright() as pw:
            return pw.chromium.executable_path
    except Exception:
        return None


def playwright_state() -> dict:
    ok, err = require_playwright()
    if err:
        return {"ready": False, "reason": err["error"], "fix": err["fix"],
                "ask_user": err["ask_user"]}
    return {"ready": True, "venv": str(venv_dir()) if venv_python() else "system"}


def browser_choice() -> dict:
    """The browser to use this time, including which one and why — never switched silently (#857)."""
    return browser_pick.resolve(bundled_chromium_path())


# ── Finding abandoned browsers (#921) ──────────────────────────────────────────
#
# web open launches the browser as an orphan, independent process. If the state file is deleted (test temp folder)
# or it is relaunched with another profile, nobody closes that browser — headless Chromes piled up and hijacked the user's
# Chrome (file open) (observed). Only ones launched with our profile are considered. The user's Chrome has a different profile and is not caught.

# Profile folder name web open uses (state_home/.browser-profile)
PROFILE_FOLDER_NAME = ".browser-profile"
# Profile path on the command line — ours always ends in .browser-profile (paths with spaces included)
_USER_DATA_DIR_PATTERN = re.compile(r'--user-data-dir=("?)(.+?[\\/]\.browser-profile)\1(?=\s|$)')
# Even if the state root is a temp folder (tests that redirect PROJECTOPS_HOME), this shape means it is ours
_LAUNCH_PATH_MARKERS = ("/.projectops/launch/", "/.projectops/agent-test/")
# Executable name before the first arg: only known browsers are cleanup targets (unknown executables are left alone)
_BROWSER_EXECUTABLE_PATTERN = re.compile(
    r"(?:^|[\\/ ])(?:chrome|chromium|chrome for testing|chrome-headless-shell|headless_shell|msedge|"
    r"microsoft edge|brave|brave browser|vivaldi|opera)(?:\.exe)?$", re.IGNORECASE)
# If the first word is a shell or interpreter it is not a browser (browser args merely appear as text in the command)
_NON_BROWSER_FIRST_WORD_PATTERN = re.compile(
    r'^"?(?:\S*[\\/])?(?:sh|bash|zsh|dash|fish|ksh|cmd|powershell|pwsh|python[\d.]*|node|ruby|perl|env|sudo)'
    r'(?:\.exe)?"?(?:\s|$)', re.IGNORECASE)
# Idle time (hours) after which it is cleaned up even if the state file points at it
STALE_REAP_IDLE_HOURS = 12
# Time (s) to leave a just-launched browser that has not written the state file yet — open waits up to about 15 s for the port
STARTING_GRACE_SECONDS = 120


def _normalized_path(path: str) -> str:
    return os.path.realpath(path).replace("\\", "/")


def is_owned_profile(profile: str) -> bool:
    """Is this a profile pro-launch launched: under the current state root · or a path shaped like .projectops/launch."""
    normalized = _normalized_path(profile)
    if any(marker in normalized for marker in _LAUNCH_PATH_MARKERS):
        return True
    return normalized.startswith(_normalized_path(str(base_dir() / "launch")) + "/")


def is_browser_executable_command(command: str) -> bool:
    """Is the command line's executable a browser (so shell·agent commands that only contain the args as text are not killed, #1027)"""
    if _NON_BROWSER_FIRST_WORD_PATTERN.match(command):
        return False
    return bool(_BROWSER_EXECUTABLE_PATTERN.search(command.split(" --", 1)[0].strip().strip('"')))


def owned_browser_processes(table: list[dict]) -> list[dict]:
    """Process list > main browser processes launched with our profile (--type= children like renderer · GPU excluded)."""
    found = []
    for row in table:
        command = row.get("command") or ""
        if ("--remote-debugging-port=" not in command or "--type=" in command
                or not is_browser_executable_command(command)):
            continue
        match = _USER_DATA_DIR_PATTERN.search(command)
        if match and is_owned_profile(match.group(2)):
            found.append({**row, "profile": match.group(2)})
    return found


def _stale_reasons(process: dict, maximum_idle_hours: float) -> tuple[list[str], dict]:
    """(cleanup reasons, state info). 3 reasons: profile_gone · state_not_pointing · idle"""
    profile = Path(process["profile"])
    state = read_state(profile.parent / _WEB_STATE) if profile.parent.is_dir() else {}
    elapsed = process.get("elapsed_seconds")
    is_starting = elapsed is None or elapsed < STARTING_GRACE_SECONDS
    idle = idle_hours(state) if state else None
    info = {"state_file": str(profile.parent / _WEB_STATE) if state else None, "idle_hours": idle}
    if not profile.is_dir():
        return ["profile_gone"], info
    if str(state.get("pid")) != str(process["pid"]):
        # A just-launched one may not have written the state file yet
        if is_starting:
            return [], info
        # The state lost its pid but the profile is in recent use: the next web open on it reattaches (#1154)
        if _is_adoptable_orphan(state, idle, maximum_idle_hours):
            return [], {**info, "adoptable": True}
        return ["state_not_pointing"], info
    # Orphaned: on POSIX it moves to PPID 1; on Windows the dead parent's number remains
    parent_pid = process.get("ppid")
    is_orphan = not parent_pid or parent_pid == 1 or not pid_alive(int(parent_pid))
    if is_orphan and idle is not None and idle >= maximum_idle_hours:
        return ["idle"], info
    return [], info


def _is_adoptable_orphan(state: dict, idle: float | None, maximum_idle_hours: float) -> bool:
    """State file exists, its own pid is gone (nothing else holds the profile) and it was used recently."""
    recorded_pid = state.get("pid")
    is_recorded_alive = bool(recorded_pid) and pid_alive(int(recorded_pid))
    return bool(state) and not is_recorded_alive and idle is not None and idle < maximum_idle_hours


def find_stale_browsers(maximum_idle_hours: float = STALE_REAP_IDLE_HOURS) -> dict:
    """Split pro-launch browsers into abandoned (stale) · in use (kept). Used by doctor and web close --stale.

    > {"readable", "stale": [{pid, profile, reasons, ...}], "kept": [...]}. readable is False if the process list cannot be read
    """
    table = process_table()
    if table is None:
        return {"readable": False, "stale": [], "kept": []}
    stale, kept = [], []
    for process in owned_browser_processes(table):
        reasons, info = _stale_reasons(process, maximum_idle_hours)
        entry = {"pid": process["pid"], "ppid": process.get("ppid"), "profile": process["profile"],
                 "elapsed_seconds": process.get("elapsed_seconds"), **info}
        (stale if reasons else kept).append({**entry, "reasons": reasons} if reasons else entry)
    return {"readable": True, "stale": stale, "kept": kept}


# Debugging port on a browser command line
_DEBUGGING_PORT_PATTERN = re.compile(r"--remote-debugging-port=(\d+)")


def running_browser_on_profile(profile: Path) -> dict | None:
    """Browser main process already running on this profile folder > {pid, cdp}. None when none or unreadable.

    One profile folder holds one browser: if it runs but the state lost it, reattach instead of a launch
    that dies on SingletonLock (#1154).
    """
    wanted = _normalized_path(str(profile))
    for process in owned_browser_processes(process_table() or []):
        port = _DEBUGGING_PORT_PATTERN.search(process.get("command") or "")
        if port and _normalized_path(process["profile"]) == wanted:
            return {"pid": process["pid"], "cdp": f"http://127.0.0.1:{port.group(1)}"}
    return None
