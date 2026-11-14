"""Identifying the agent host process: pid · start time of the agent that made this call (Claude Code·Codex·Cursor, etc.) (#953).

This is what keeps a device lease "only while the session is alive". Walks up ancestor processes to the first agent command line.
None if not found — the caller decides by the idle limit alone.
"""
from __future__ import annotations

import os
import re
import time

from pro_launch.runtime import procs

# Agent host command lines (a new agent tool is one line here)
AGENT_HOST_PATTERNS = (
    re.compile(r"^(\S*[\\/])?(claude|codex|gemini|opencode)(\.exe)?(\s|$)", re.IGNORECASE),
    re.compile(r"^(\S*[\\/])?node(\.exe)?\s+(\S*[\\/])?(claude|codex|gemini)(\.js)?(\s|$)", re.IGNORECASE),
    re.compile(r"[\\/]Cursor\.app[\\/]|(^|[\\/])Cursor\.exe", re.IGNORECASE),
)
# For tools not in the patterns — give the host pid directly
HOST_PID_ENV_VAR = "LAUNCH_HOST_PID"
# Max steps up the ancestor chain (guards against ppid cycles)
MAXIMUM_ANCESTOR_DEPTH = 64
# Same pid but start time off by this much means a different process (pid reuse) (s)
START_TIME_TOLERANCE_SECONDS = 5


def is_agent_host_command(command: str) -> bool:
    return any(pattern.search(command or "") for pattern in AGENT_HOST_PATTERNS)


def _started_at(row: dict, now: float) -> float | None:
    elapsed = row.get("elapsed_seconds")
    return now - elapsed if elapsed is not None else None


def find_agent_host(process_rows: list[dict] | None = None, start_pid: int | None = None) -> dict | None:
    """Agent host > {pid, started_at}. Env var override > first match up the ancestor chain. None if none."""
    if process_rows is not None:
        row_by_pid = {row["pid"]: row for row in process_rows}
        lookup = row_by_pid.get
    else:
        lookup = procs.read_process
    now = time.time()
    override = (os.environ.get(HOST_PID_ENV_VAR) or "").strip()
    if override.isdigit():
        row = lookup(int(override))
        return {"pid": int(override), "started_at": _started_at(row, now) if row else None}
    current = lookup(start_pid if start_pid is not None else os.getpid())
    # Skip ourselves (the launch_cli path may contain .cursor etc.)
    for _ in range(MAXIMUM_ANCESTOR_DEPTH):
        if current is None:
            return None
        parent = lookup(current.get("ppid"))
        if parent is None or parent["pid"] == current["pid"]:
            return None
        if is_agent_host_command(parent.get("command", "")):
            return {"pid": parent["pid"], "started_at": _started_at(parent, now)}
        current = parent
    return None


def is_host_alive(host: dict | None, process_rows: list[dict] | None = None) -> bool | None:
    """Is the recorded host still that process. No record·list unreadable > None, gone or pid reused > False."""
    if not host or not host.get("pid"):
        return None
    if process_rows is not None:
        row = next((r for r in process_rows if r["pid"] == host["pid"]), None)
    elif procs.pid_alive(host["pid"]):
        row = procs.read_process(host["pid"])
        if row is None:
            return None
    else:
        return False
    if row is None:
        return False
    recorded, current = host.get("started_at"), _started_at(row, time.time())
    if recorded is None or current is None:
        return True
    return abs(current - recorded) <= START_TIME_TOLERANCE_SECONDS
