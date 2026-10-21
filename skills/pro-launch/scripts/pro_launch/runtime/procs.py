"""프로세스 확인 · 종료 — pro_launch 안의 OS 분기는 전부 여기서 갈린다 (생존 확인 원본은 common/proc.py)."""
from __future__ import annotations

import json
import os
import re
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
    # 정상 종료는 본 프로세스에만 — 그룹 전체에 보내면 쿠키·로그인을 디스크에 쓰기 전에 끝난다 (실측, #956)
    # 안 죽으면 그룹 전체를 강제 종료 (새 세션으로 띄웠으므로 pid 가 프로세스 그룹 id 이기도 하다)
    for sig, wait, is_group in ((signal.SIGTERM, grace, False), (signal.SIGKILL, 3.0, True)):
        _send_signal(pid, sig, is_group)
        end = time.time() + wait
        while time.time() < end:
            if not pid_alive(pid):
                if not is_group:
                    _send_signal(pid, signal.SIGKILL, True)   # 남은 렌더러 정리
                return False
            time.sleep(0.1)
    return pid_alive(pid)


def _send_signal(pid: int, sig, is_group: bool) -> None:
    try:
        if is_group:
            os.killpg(pid, sig)
        else:
            os.kill(pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        if is_group:
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError, OSError):
                pass


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
            r = subprocess.run(["ps", "-ax", "-ww", "-o", "command="], capture_output=True, text=True,
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


def interrupt_process(pid: int, wait_seconds: float = 10.0) -> bool:
    """SIGINT 를 보내 스스로 마무리하게 한다 (녹화 파일을 닫게). 끝났으면 True. 윈도우는 정상 종료 요청으로 대신한다."""
    if sys.platform == "win32":
        return not kill_browser(pid, wait_seconds)
    try:
        os.kill(pid, signal.SIGINT)
    except (ProcessLookupError, PermissionError, OSError):
        return True
    end = time.time() + wait_seconds
    while time.time() < end:
        if not pid_alive(pid):
            return True
        time.sleep(0.1)
    return not pid_alive(pid)


def kill_process_group(pid: int, grace: float = 5.0) -> bool:
    """새 세션으로 띄운 프로세스와 그 자식(예: 중계 > maestro mcp > java)을 함께 끝낸다. 살아 있으면 True."""
    return kill_browser(pid, grace)


def elapsed_seconds_from_ps(etime: str) -> int | None:
    """ps etime([[일-]시:]분:초) > 초. 못 읽으면 None."""
    try:
        days, _, clock = etime.strip().rpartition("-")
        parts = [int(part) for part in clock.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        hours, minutes, seconds = parts[-3:]
        return (int(days) if days else 0) * 86400 + hours * 3600 + minutes * 60 + seconds
    except ValueError:
        return None


def _process_table_windows() -> list[dict] | None:
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine } | ForEach-Object { "
              "[pscustomobject]@{pid=$_.ProcessId; ppid=$_.ParentProcessId; command=$_.CommandLine; "
              "elapsed_seconds=[int]((Get-Date) - $_.CreationDate).TotalSeconds } } | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
        rows = json.loads(r.stdout or "[]")
    except Exception:
        return None
    return rows if isinstance(rows, list) else [rows]


def process_table() -> list[dict] | None:
    """떠 있는 프로세스 목록 > [{pid, ppid, elapsed_seconds, command}]. 읽지 못하면 None.

    elapsed_seconds: 뜬 지 몇 초 (못 읽으면 None) — 막 띄운 것을 치우지 않는 근거
    """
    if sys.platform == "win32":
        return _process_table_windows()
    try:
        r = subprocess.run(["ps", "-ax", "-ww", "-o", "pid=,ppid=,etime=,command="], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=5)
    except Exception:
        return None
    rows = []
    for line in (r.stdout or "").splitlines():
        fields = line.split(None, 3)
        if len(fields) < 4 or not fields[0].isdigit() or not fields[1].isdigit():
            continue
        rows.append({"pid": int(fields[0]), "ppid": int(fields[1]),
                     "elapsed_seconds": elapsed_seconds_from_ps(fields[2]), "command": fields[3]})
    return rows or None


def read_process(pid: int) -> dict | None:
    """프로세스 하나 > {pid, ppid, elapsed_seconds, command}. 없거나 못 읽으면 None (전체 목록보다 빠르다)."""
    if sys.platform == "win32":
        return next((row for row in process_table() or [] if row["pid"] == pid), None)
    try:
        result = subprocess.run(["ps", "-ww", "-o", "pid=,ppid=,etime=,command=", "-p", str(pid)],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    fields = (result.stdout or "").strip().split(None, 3)
    if len(fields) < 4 or not fields[0].isdigit() or not fields[1].isdigit():
        return None
    return {"pid": int(fields[0]), "ppid": int(fields[1]),
            "elapsed_seconds": elapsed_seconds_from_ps(fields[2]), "command": fields[3]}


def try_lock_file(handle) -> bool:
    """열린 파일에 배타 잠금을 시도한다 (기다리지 않음). macOS·Linux flock · Windows msvcrt (기기 원장, #953)."""
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def unlock_file(handle) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass   # 파일을 닫으면 OS 가 잠금을 푼다


def clone_tree(source: str, target: str) -> tuple[bool, str]:
    """폴더 복제 > (성공, 오류). macOS 는 APFS 복제(cp -c, 블록 공유) · Linux 는 reflink 가능하면 · 그 밖은 일반 복사 (#959)."""
    if sys.platform == "darwin":
        command = ["cp", "-c", "-R", source, target]
    elif sys.platform.startswith("linux"):
        command = ["cp", "-R", "--reflink=auto", source, target]
    else:
        import shutil
        try:
            shutil.copytree(source, target)
        except OSError as error:
            return False, str(error)
        return True, ""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    return result.returncode == 0, (result.stderr or "").strip()[-300:]


def read_windows_memory() -> dict | None:
    """Windows 메모리 > {total_mb, available_mb, swap_total_mb, swap_used_mb}. Windows 가 아니면 None (#964).

    GlobalMemoryStatusEx — 페이지 파일(commit) 중 물리 메모리를 뺀 몫을 스왑으로 본다.
    """
    if sys.platform != "win32":
        return None
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    mebibyte = 1024 * 1024
    swap_total = max(0, status.ullTotalPageFile - status.ullTotalPhys)
    swap_free = max(0, status.ullAvailPageFile - status.ullAvailPhys)
    return {"total_mb": status.ullTotalPhys // mebibyte, "available_mb": status.ullAvailPhys // mebibyte,
            "swap_total_mb": swap_total // mebibyte, "swap_used_mb": max(0, swap_total - swap_free) // mebibyte}


def process_memory_mb(pids: list[int]) -> int:
    """프로세스들의 상주 메모리 합 (MB). 못 읽은 것은 0 — 기기 비용 측정용 (#964)."""
    if not pids:
        return 0
    try:
        if sys.platform == "win32":
            pid_list = ",".join(str(pid) for pid in pids)
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                f"(Get-Process -Id {pid_list} -ErrorAction SilentlyContinue | "
                                "Measure-Object WorkingSet64 -Sum).Sum"],
                               capture_output=True, text=True, timeout=15)
            total_bytes = int(float((r.stdout or "0").strip() or 0))
            return total_bytes // (1024 * 1024)
        if sys.platform == "darwin":
            # RSS 는 압축·스왑된 몫을 빼서 크게 줄어든다 (실측: 에뮬레이터 RSS 245MB, top MEM 5.6GB) — top 의 footprint
            command = ["top", "-l", "1", "-stats", "pid,mem"]
            for pid in pids:
                command += ["-pid", str(pid)]
            r = subprocess.run(command, capture_output=True, text=True, timeout=20)
            return sum(_size_to_mb(fields[1]) for fields in (line.split() for line in (r.stdout or "").splitlines())
                       if len(fields) == 2 and fields[0].isdigit() and int(fields[0]) in pids)
        r = subprocess.run(["ps", "-o", "rss=", "-p", ",".join(str(pid) for pid in pids)],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0
    return sum(int(line) for line in (r.stdout or "").split() if line.isdigit()) // 1024


def _size_to_mb(text: str) -> int:
    """top 크기 표기 (512K · 5611M · 1.2G, 끝의 +/- 무시) > MB."""
    match = re.match(r"^([\d.]+)([KMGT]?)", text.rstrip("+-"))
    if not match:
        return 0
    scale = {"": 1 / (1024 * 1024), "K": 1 / 1024, "M": 1, "G": 1024, "T": 1024 * 1024}[match.group(2)]
    return int(float(match.group(1)) * scale)


def top_memory_processes(count: int) -> list[dict]:
    """메모리를 가장 많이 쓰는 프로세스 > [{pid, name, memory_mb}] (#964).

    macOS 는 top footprint(압축·스왑 포함 — RSS 는 VM·에뮬레이터를 크게 줄여 보인다), Windows 는 WorkingSet, 그 밖은 RSS.
    """
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["top", "-l", "1", "-o", "mem", "-n", str(count), "-stats", "pid,mem,command"],
                               capture_output=True, text=True, timeout=20)
            rows = []
            for line in (r.stdout or "").splitlines():
                fields = line.split(None, 2)
                if len(fields) == 3 and fields[0].isdigit():
                    rows.append({"pid": int(fields[0]), "name": fields[2].strip(), "memory_mb": _size_to_mb(fields[1])})
            return rows[:count]
        if sys.platform == "win32":
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                f"Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First {count} "
                                "| ForEach-Object { \"$($_.Id) $([int]($_.WorkingSet64/1MB)) $($_.ProcessName)\" }"],
                               capture_output=True, text=True, timeout=20)
        else:
            r = subprocess.run(["ps", "-axo", "pid=,rss=,comm=", "--sort=-rss"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in (r.stdout or "").splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            size = int(fields[1]) if sys.platform == "win32" else int(fields[1]) // 1024
            rows.append({"pid": int(fields[0]), "name": os.path.basename(fields[2].strip()), "memory_mb": size})
    return rows[:count]


def process_ids_with_text(text: str) -> list[int]:
    """명령줄에 text 가 들어 있는 프로세스 pid (예: 시뮬레이터 UDID — 그 기기의 프로세스 묶음). 우리 프로세스는 뺀다."""
    rows = process_table() or []
    return [row["pid"] for row in rows if text in (row.get("command") or "") and row["pid"] != os.getpid()]


# 클립보드 읽기 명령 — OS 별, 위에서부터 있는 것
_CLIPBOARD_COMMANDS = {
    "darwin": (["pbpaste"],),
    "win32": (["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],),
    "linux": (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"],
              ["xsel", "--clipboard", "--output"]),
}


def read_system_clipboard() -> tuple[str | None, str | None]:
    """호스트 클립보드 글자 > (값, 실패 사유). macOS pbpaste · Windows Get-Clipboard · Linux wl-paste/xclip/xsel."""
    platform_key = "linux" if sys.platform.startswith("linux") else sys.platform
    for command in _CLIPBOARD_COMMANDS.get(platform_key, ()):
        try:
            r = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=5)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0:
            return r.stdout, None
    return None, f"No command to read the clipboard on this OS ({sys.platform})"


def process_ids_with_arguments(*arguments: str) -> list[int]:
    """명령줄에 arguments 가 이 순서로 붙어 나오는 프로세스 pid (예: "-avd", "Pixel" — 이름 일부만 맞는 것은 뺀다).

    읽지 못하면 빈 목록. 우리 프로세스는 뺀다.
    """
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                 "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine } "
                 "| ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        else:
            r = subprocess.run(["ps", "-ax", "-ww", "-o", "pid=,command="], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=5)
    except Exception:
        return []
    wanted = list(arguments)
    found = []
    for line in (r.stdout or "").splitlines():
        head, _, command = line.strip().partition(" ")
        if not head.isdigit() or int(head) == os.getpid():
            continue
        tokens = command.split()
        if any(tokens[i:i + len(wanted)] == wanted for i in range(len(tokens))):
            found.append(int(head))
    return found


def force_kill(pid: int) -> bool:
    """정상 종료를 거치지 않고 바로 끝낸다 (emu kill 이 안 먹는 에뮬레이터 qemu). 살아 있으면 True."""
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    end = time.time() + 3.0
    while time.time() < end:
        if not pid_alive(pid):
            return False
        time.sleep(0.1)
    return pid_alive(pid)
