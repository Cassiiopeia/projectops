"""`web script` 실행 중 브라우저 메모리 감시 — 상한을 넘으면 조각을 멈춘다 (#973).

실측: 수천 페이지를 브라우저 안에서 도는 조각이 Chrome 을 275GB · 스왑 40GB 까지 키웠고 browser_hung 이 5번 났다.
브라우저 본 프로세스 + 자식(렌더러·GPU) RSS 합을 `ps` 로 재고, 상한을 넘으면 조각 프로세스를 죽인다.
`ps` 가 없는 곳(Windows)은 재지 않고 시간 상한만 본다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Callable

# 브라우저 프로세스 묶음 RSS 상한 기본값 (MB) — 조각 하나가 컴퓨터를 멈추지 않을 선
DEFAULT_BROWSER_MEMORY_LIMIT_MEGABYTES = 8192
# 상한을 바꾸는 환경변수 (MB) — --memory-limit-mb 가 있으면 그것이 이긴다
BROWSER_MEMORY_LIMIT_ENV = "PRO_LAUNCH_BROWSER_MEMORY_LIMIT_MB"
# 메모리를 다시 재는 간격 (초)
MEMORY_SAMPLE_INTERVAL_SECONDS = 2.0
KILOBYTES_PER_MEGABYTE = 1024


def resolve_limit_megabytes(option_value: int | None) -> int:
    """상한 (MB): --memory-limit-mb > 환경변수 > 기본값. 잘못된 환경변수 값은 기본값."""
    if option_value and option_value > 0:
        return option_value
    try:
        from_env = int(os.environ.get(BROWSER_MEMORY_LIMIT_ENV) or 0)
    except ValueError:
        from_env = 0
    return from_env if from_env > 0 else DEFAULT_BROWSER_MEMORY_LIMIT_MEGABYTES


def read_process_table() -> list[tuple[int, int, int]] | None:
    """[(pid, ppid, rss KB)]. ps 가 없거나 못 읽으면 None (감시를 건너뛴다)."""
    if not shutil.which("ps"):
        return None
    try:
        completed = subprocess.run(["ps", "-axo", "pid=,ppid=,rss="], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            rows.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return rows or None


def tree_rss_megabytes(table: list[tuple[int, int, int]], root_pid: int) -> int | None:
    """root_pid 와 그 자손 전부의 RSS 합 (MB). root 가 표에 없으면 None (이미 끝난 브라우저)."""
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
    """조각 프로세스를 돌리며 브라우저 RSS 를 잰다 > {status: done|timeout|memory_exceeded, ...}.

    시간 · 메모리 상한을 넘으면 조각 프로세스를 죽이고 거둔다 (브라우저 정리는 부르는 쪽).
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
            # 다시 부를 때 입력을 또 보내지 않는다 (communicate 가 이미 보낸 것을 기억)
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
