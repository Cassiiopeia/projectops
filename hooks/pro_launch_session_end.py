"""Claude Code SessionEnd hook: returns devices leased by the ended session (#953), closes browsers it opened (#956) and releases its desktop input session (#985).

Input: session_id from stdin JSON. Runs `device release --all` · `web close --session-end` · `desktop session stop` only when that session has a lease, browser or input session
(otherwise exits at once — so session end is not delayed). Always exit code 0.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1])
LAUNCH_CLI = PLUGIN_ROOT / "skills" / "pro-launch" / "scripts" / "launch_cli.py"
LAUNCH_SCRIPTS = LAUNCH_CLI.parent
RELEASE_TIMEOUT_SECONDS = 25


def _use_launch_modules() -> None:
    """Add the path so pro-launch source modules can be imported."""
    for path in (str(PLUGIN_ROOT / "scripts"), str(LAUNCH_SCRIPTS)):
        if path not in sys.path:
            sys.path.insert(0, path)


def session_has_leases(session_id: str) -> bool:
    """Does the ledger hold any lease for that session (ledger reads use the pro-launch source). False if unreadable."""
    _use_launch_modules()
    try:
        from pro_launch.runtime.device_ledger import read_ledger
    except ImportError:
        return False
    return any(lease.get("session") == session_id
               for entry in read_ledger()["devices"].values() for lease in entry["leases"])


def session_has_browsers(session_id: str) -> bool:
    """Is there a browser state file opened by this session (#956)."""
    _use_launch_modules()
    try:
        from pro_launch.runtime.browser import read_state
        from pro_launch.runtime.browser_profiles import all_web_state_files
    except ImportError:
        return False
    return any(read_state(path).get("opened_by_session") == session_id for path in all_web_state_files())


def session_holds_desktop(session_id: str) -> bool:
    """Does this session hold the desktop input session (keyboard, mouse) (#985)."""
    _use_launch_modules()
    try:
        from pro_launch.runtime.desktop_state import current_holder
    except ImportError:
        return False
    holder = current_holder()
    return bool(holder) and holder.get("session") == session_id


def main(stdin_text: str, environ: dict) -> int:
    try:
        session_id = (json.loads(stdin_text or "{}") or {}).get("session_id")
    except (json.JSONDecodeError, AttributeError):
        return 0
    if not session_id:
        return 0
    commands = []
    if session_has_leases(session_id):
        commands.append(["device", "release", "--all"])
    if session_has_browsers(session_id):
        commands.append(["web", "close", "--session-end"])
    if session_holds_desktop(session_id):
        commands.append(["desktop", "session", "stop"])
    for command in commands:
        try:
            subprocess.run([sys.executable, str(LAUNCH_CLI), *command],
                           env={**environ, "LAUNCH_SESSION": session_id, "PYTHONIOENCODING": "utf-8"},
                           capture_output=True, timeout=RELEASE_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError):
            pass   # Failure must not block session end — devices free up when the host exits, and web close --stale collects browsers
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin.read() if not sys.stdin.isatty() else "", dict(os.environ)))
