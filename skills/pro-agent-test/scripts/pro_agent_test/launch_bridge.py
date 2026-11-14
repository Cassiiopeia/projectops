"""Hand-off to pro-launch: launch_cli.py subprocess calls, forwarding of moved commands"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from common.emit import emit


# =========================================================================
# Commands moved to pro-launch — hand-off layer (#631)
# =========================================================================
#
# Skills never import each other in Python. Call launch_cli.py in the same plugin as a
# subprocess, return the result as is, and add a next saying "use that one now".
# This layer is removed in the next minor.

MOVED = ("doctor", "devices", "device", "web", "access", "db", "logs", "shrink",
         "get-output-path")

# skills/pro-launch/scripts/launch_cli.py (this file: skills/pro-agent-test/scripts/pro_agent_test/)
_LAUNCH_CLI = Path(__file__).resolve().parents[3] / "pro-launch" / "scripts" / "launch_cli.py"


def _launch(argv: list[str]) -> tuple[dict | None, str, int]:
    """Call launch_cli and return (JSON, raw text, exit code). stdin is not passed."""
    if not _LAUNCH_CLI.is_file():
        return None, "", 1
    r = subprocess.run([sys.executable, str(_LAUNCH_CLI), *argv], capture_output=True,
                       text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    try:
        data = json.loads((r.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        data = None
    return data, (r.stdout or "") + (r.stderr or ""), r.returncode


def delegate(argv: list[str]) -> int:
    """Forward a moved command to pro-launch. Outputs still land in the agent-test folder."""
    cmd = argv[0]
    if cmd == "get-output-path" and "--skill" not in argv:
        argv = [*argv, "--skill", "agent-test"]
    data, raw, rc = _launch(argv)
    if data is None and rc == 0 and raw.strip():
        # Normal non-JSON output such as --help — show as is
        sys.stdout.write(raw)
        return 0
    if data is None:
        return emit({"ok": False, "code": "launch_unavailable",
                     "error": f"Could not call pro-launch's launch_cli.py ({_LAUNCH_CLI})",
                     "output": raw[-400:],
                     "hint": "Check that projectops is fully installed — pro-launch must be installed with it"})
    moved = f"use pro-launch's launch_cli.py {cmd} (e2e_cli {cmd} is removed in the next minor)"
    data["moved_to"] = f"launch_cli.py {cmd}"
    data["next"] = f"{data['next']} · {moved}" if data.get("next") else moved
    return emit(data)
