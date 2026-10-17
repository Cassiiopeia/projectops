"""프로세스 확인 · 종료 — pro_launch 안의 OS 분기는 전부 여기서 갈린다 (생존 확인 원본은 common/proc.py)."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

# 생존 확인은 scripts/common 단일 원본 (common/state.py 와 공용) — 여기서는 재노출
from common.proc import _pid_alive_windows, pid_alive  # noqa: F401


def _kill_browser_windows(pid: int, grace: float) -> bool:
    """taskkill /T 로 자식 렌더러까지 정리한다. 정상 종료를 먼저, 안 죽으면 /F."""
    for force, wait in ((False, grace), (True, 3.0)):
        cmd = ["taskkill", "/PID", str(pid), "/T"] + (["/F"] if force else [])
        try:
            subprocess.run(cmd, capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
        end = time.time() + wait
        while time.time() < end:
            if not _pid_alive_windows(pid):
                return False
            time.sleep(0.1)
    return _pid_alive_windows(pid)


def kill_browser(pid: int, grace: float = 5.0) -> bool:
    """브라우저를 직접 정리한다. 정상 종료를 기다리다 안 죽으면 강제 종료한다. 살아 있으면 True.

    CDP 로 붙어 close() 를 부르면 응답 없는 브라우저에서 제한 없이 멈춘다 (#712).
    독립 프로세스로 띄웠으니 신호로 끝내는 편이 확실하다.
    """
    if sys.platform == "win32":
        return _kill_browser_windows(pid, grace)
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 3.0)):
        try:
            # 새 세션으로 띄웠으므로 pid 가 프로세스 그룹 id 이기도 하다 — 자식 렌더러까지 함께 정리
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        end = time.time() + wait
        while time.time() < end:
            if not pid_alive(pid):
                return False
            time.sleep(0.1)
    return pid_alive(pid)


def detach_options() -> dict:
    """브라우저를 우리가 끝나도 살아 있게 띄우는 Popen 옵션 (POSIX 의 새 세션에 해당하는 것)."""
    if sys.platform == "win32":
        return {"creationflags": 0x00000008 | 0x00000200}   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    return {"start_new_session": True}


def process_command_lines() -> str | None:
    """떠 있는 모든 프로세스의 명령줄을 한 덩어리로. 읽지 못하면 None.

    윈도우엔 ps 가 없고, 한글 경로가 든 명령줄은 기본 코드페이지로 읽으면 디코딩이 깨져
    stdout 이 None 이 된다 — 인코딩을 명시한다.
    """
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                 "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine } "
                 "| ForEach-Object { $_.CommandLine }) -join \"`n\""],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        else:
            r = subprocess.run(["ps", "-ax", "-o", "command="], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=5)
    except Exception:
        return None
    return r.stdout or None


def manual_kill_command(pid: int) -> str:
    """사용자가 직접 브라우저를 끝낼 때 칠 명령."""
    return f"taskkill /PID {pid} /T /F" if sys.platform == "win32" else f"kill -9 {pid}"


def spawn_detached(command: list[str], working_folder: str, log_path) -> int:
    """우리가 끝나도 살아 있는 백그라운드 프로세스를 띄운다 > pid. 표준오류는 log_path 로 (덮어쓴다)."""
    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=log_file, cwd=working_folder, **detach_options())
    return process.pid


def kill_process_group(pid: int, grace: float = 5.0) -> bool:
    """새 세션으로 띄운 프로세스와 그 자식(예: 중계 > maestro mcp > java)을 함께 끝낸다. 살아 있으면 True."""
    return kill_browser(pid, grace)
