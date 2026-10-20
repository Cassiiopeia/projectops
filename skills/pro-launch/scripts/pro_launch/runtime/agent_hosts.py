"""agent 호스트 프로세스 판별: 이 호출을 낸 agent(Claude Code·Codex·Cursor 등)의 pid · 시작 시각 (#953).

기기 lease 가 "세션이 살아 있는 동안만" 유지되게 하는 근거다. 조상 프로세스를 올라가며 첫 agent 명령줄을 찾는다.
못 찾으면 None — 부르는 쪽은 유휴 한도만으로 판정한다.
"""
from __future__ import annotations

import os
import re
import time

from pro_launch.runtime import procs

# agent 호스트 명령줄 (새 agent 도구는 여기에 한 줄)
AGENT_HOST_PATTERNS = (
    re.compile(r"^(\S*[\\/])?(claude|codex|gemini|opencode)(\.exe)?(\s|$)", re.IGNORECASE),
    re.compile(r"^(\S*[\\/])?node(\.exe)?\s+(\S*[\\/])?(claude|codex|gemini)(\.js)?(\s|$)", re.IGNORECASE),
    re.compile(r"[\\/]Cursor\.app[\\/]|(^|[\\/])Cursor\.exe", re.IGNORECASE),
)
# 패턴에 없는 도구용 — 호스트 pid 를 직접 준다
HOST_PID_ENV_VAR = "LAUNCH_HOST_PID"
# 조상 체인 최대 단계 (ppid 순환 대비)
MAXIMUM_ANCESTOR_DEPTH = 64
# 같은 pid 라도 시작 시각이 이만큼 어긋나면 다른 프로세스(pid 재사용)로 본다 (초)
START_TIME_TOLERANCE_SECONDS = 5


def is_agent_host_command(command: str) -> bool:
    return any(pattern.search(command or "") for pattern in AGENT_HOST_PATTERNS)


def _started_at(row: dict, now: float) -> float | None:
    elapsed = row.get("elapsed_seconds")
    return now - elapsed if elapsed is not None else None


def find_agent_host(process_rows: list[dict] | None = None, start_pid: int | None = None) -> dict | None:
    """agent 호스트 > {pid, started_at}. 환경변수 지정 > 조상 체인 첫 일치. 없으면 None."""
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
    # 자기 자신은 건너뛴다 (launch_cli 경로에 .cursor 등이 들어 있을 수 있다)
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
    """기록된 호스트가 아직 그 프로세스인가. 기록 없음·목록 못 읽음 > None, 사라졌거나 pid 재사용 > False."""
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
