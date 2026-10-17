"""`web open` 자가 복구: 기록된 브라우저 상태 판정 (죽음·멈춤·정상) > 남은 프로필 잠금 정리 (#887).

크래시·창 닫기 뒤 `browser_start_failed` 가 나면 agent 가 pid 확인·잠금 삭제·재시도를 손으로 했다.
여기서 한 번에 판정하고, 치운 것을 `recovered` 로 돌려준다. 끄는 것은 상태 파일에 적힌(우리가 띄운) pid 뿐이다.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from pro_launch.runtime.procs import kill_browser, pid_alive, process_command_lines

# Chromium 이 프로필에 남기는 잠금 3개 (macOS·Linux 는 SingletonLock 이 "호스트-pid" 를 가리키는 심볼릭 링크)
PROFILE_LOCK_NAMES = ("SingletonLock", "SingletonSocket", "SingletonCookie")
# CDP 가 이 시간 안에 답하지 않으면 멈춘 브라우저로 본다 (초)
HUNG_PROBE_SECONDS = 3.0
# 멈춘 브라우저는 정상 종료를 오래 기다려도 소용없다 — 짧게 기다리고 강제 종료 (초)
HUNG_KILL_GRACE_SECONDS = 1.0
# 실패 응답에 싣는 브라우저 표준오류 끝 줄 수
STDERR_TAIL_LINES = 12
BROWSER_STDERR_FILE = "browser-stderr.log"


def profile_in_use(profile: Path) -> bool:
    """이 프로필로 떠 있는 브라우저 프로세스가 있나. 확인 못 하면 쓰는 중으로 본다 (남의 잠금을 지우지 않는다)."""
    command_lines = process_command_lines()
    if not command_lines:
        return True
    # 윈도우는 공백 경로를 따옴표로 감싸므로 인자 이름이 아니라 경로 자체로 찾는다
    return str(profile) in command_lines


def has_profile_lock(profile: Path) -> bool:
    # 대상이 사라진 심볼릭 링크도 잠금이다 — exists() 는 링크를 따라가 False 를 낸다
    return any(os.path.lexists(profile / name) for name in ("SingletonLock", "SingletonSocket"))


def clear_stale_locks(profile: Path) -> bool:
    """아무 프로세스도 프로필을 안 쓸 때만 잠금을 지운다. 지운 것이 있으면 True."""
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
    """CDP 엔드포인트가 제한 시간 안에 버전 정보를 주나. Playwright 연결은 멈춘 브라우저에서 제한 없이 기다린다."""
    try:
        with urllib.request.urlopen(f"{cdp.rstrip('/')}/json/version", timeout=timeout) as response:
            return "Browser" in json.loads(response.read().decode("utf-8", "replace"))
    except Exception:
        return False


def recover_recorded_browser(previous_state: dict, profile: Path) -> tuple[str, list[str]]:
    """기록된 브라우저 판정 > ("reuse" | "launch" | "blocked", 치운 것 목록).

    살아 있고 CDP 응답 > reuse · 살아 있는데 무응답 > 멈춤으로 보고 종료 · 죽음 > 잠금만 정리.
    blocked: 멈춘 브라우저를 끄지 못했다.
    """
    recovered: list[str] = []
    pid = previous_state.get("pid")
    cdp = previous_state.get("cdp")
    if pid and pid_alive(int(pid)):
        if cdp and cdp_responds(cdp):
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
    """브라우저 표준오류 마지막 줄들. 없으면 None."""
    try:
        lines = [line.rstrip() for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()]
    except OSError:
        return None
    lines = [line for line in lines if line]
    return lines[-line_count:] or None
