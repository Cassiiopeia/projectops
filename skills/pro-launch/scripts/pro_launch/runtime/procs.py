"""프로세스 확인 · 종료 — OS 마다 다른 것은 전부 여기서 갈린다 (`sys.platform` 분기는 이 파일에만 둔다)."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def pid_alive(pid: int) -> bool:
    """프로세스가 살아 있나. 우리가 띄운 자식이 좀비로 남은 경우는 거둬들이고 죽은 것으로 본다."""
    if sys.platform == "win32":
        return _pid_alive_windows(pid)
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)   # 자식이면 거둬들인다 (아니면 ChildProcessError)
        if done:
            return False
    except ChildProcessError:
        pass
    except OSError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid_alive_windows(pid: int) -> bool:
    """윈도우는 os.kill(pid, 0) 이 프로세스를 **종료**시킨다. 핸들을 열어 종료 코드를 본다."""
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259   # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


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


def manual_kill_command(pid: int) -> str:
    """사용자가 직접 브라우저를 끝낼 때 칠 명령."""
    return f"taskkill /PID {pid} /T /F" if sys.platform == "win32" else f"kill -9 {pid}"
