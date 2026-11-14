"""Browser memory watch while `web script` runs — stops the snippet when over the limit (#973).

Observed: a snippet walking thousands of pages inside the browser grew Chrome to 275GB with 40GB swap and caused browser_hung 5 times.
Measures the RSS sum of the main browser process + children (renderers, GPU) with `ps`, and kills the snippet process when over the limit.
Where `ps` is missing (Windows), memory isn't measured and only the time limit applies.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Callable

# Default RSS limit (MB) for the browser process group — the line where one snippet won't freeze the computer
# The RSS sum double-counts memory shared between renderers, so keep it generous (catch the real 275GB incident, don't kill normal multi-tab sessions)
DEFAULT_BROWSER_MEMORY_LIMIT_MEGABYTES = 32768
# Environment variable overriding the limit (MB) — --memory-limit-mb wins if given
BROWSER_MEMORY_LIMIT_ENV = "PRO_LAUNCH_BROWSER_MEMORY_LIMIT_MB"
# Interval (seconds) between memory measurements
MEMORY_SAMPLE_INTERVAL_SECONDS = 2.0
KILOBYTES_PER_MEGABYTE = 1024


def resolve_limit_megabytes(option_value: int | None) -> int:
    """Limit (MB): --memory-limit-mb > environment variable > default. Invalid environment values fall back to the default."""
    if option_value and option_value > 0:
        return option_value
    try:
        from_env = int(os.environ.get(BROWSER_MEMORY_LIMIT_ENV) or 0)
    except ValueError:
        from_env = 0
    return from_env if from_env > 0 else DEFAULT_BROWSER_MEMORY_LIMIT_MEGABYTES


def read_process_table() -> list[tuple[int, int, int]] | None:
    """[(pid, ppid, rss KB)]. None if ps is missing or unreadable (skip the watch)."""
    if not shutil.which("ps"):
        return None
    try:
        completed = subprocess.run(["ps", "-axo", "pid=,ppid=,rss="], capture_output=True, text=True, errors="replace", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            rows.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return rows or None


def tree_rss_megabytes(table: list[tuple[int, int, int]], root_pid: int) -> int | None:
    """RSS sum (MB) of root_pid and all its descendants. None if root is not in the table (browser already gone)."""
    rss_by_pid = {pid: rss for pid, _ppid, rss in table}
    if root_pid not in rss_by_pid:
        return None
    children_by_parent: dict[int, list[int]] = {}
    for pid, ppid, _rss in table:
        children_by_parent.setdefault(ppid, []).append(pid)
    total_kilobytes, pending, seen = 0, [root_pid], set()
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        total_kilobytes += rss_by_pid.get(pid, 0)
        pending.extend(children_by_parent.get(pid, []))
    return total_kilobytes // KILOBYTES_PER_MEGABYTE


def browser_rss_megabytes(browser_pid: int) -> int | None:
    table = read_process_table()
    return tree_rss_megabytes(table, browser_pid) if table else None


def run_with_memory_cap(command: list[str], input_text: str, timeout_seconds: float, browser_pid: int | None,
                        limit_megabytes: int, env: dict | None = None,
                        read_rss: Callable[[int], int | None] = browser_rss_megabytes) -> dict:
    """Run the snippet process while measuring browser RSS > {status: done|timeout|memory_exceeded, ...}.

    Past the time or memory limit, kill and reap the snippet process (the caller cleans up the browser).
    """
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", env=env)
    deadline = time.monotonic() + timeout_seconds
    pending_input: str | None = input_text
    peak_megabytes: int | None = None
    while True:
        wait_seconds = max(min(MEMORY_SAMPLE_INTERVAL_SECONDS, deadline - time.monotonic()), 0.05)
        try:
            stdout_text, stderr_text = process.communicate(pending_input, timeout=wait_seconds)
            return {"status": "done", "stdout": stdout_text, "stderr": stderr_text,
                    "peak_rss_megabytes": peak_megabytes}
        except subprocess.TimeoutExpired:
            # Don't send input again on later calls (communicate remembers what it already sent)
            pending_input = None
        rss_megabytes = read_rss(browser_pid) if browser_pid else None
        if rss_megabytes is not None:
            peak_megabytes = max(peak_megabytes or 0, rss_megabytes)
        if rss_megabytes is not None and rss_megabytes > limit_megabytes:
            _kill_and_reap(process)
            return {"status": "memory_exceeded", "rss_megabytes": rss_megabytes}
        if time.monotonic() >= deadline:
            _kill_and_reap(process)
            return {"status": "timeout", "peak_rss_megabytes": peak_megabytes}


def _kill_and_reap(process: subprocess.Popen) -> None:
    process.kill()
    try:
        process.communicate(timeout=5)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
