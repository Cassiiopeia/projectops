"""Process checks · termination — every OS branch in pro_launch splits here (liveness source is common/proc.py)."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time

# Liveness checks have a single source in scripts/common (shared with common/state.py) — re-exported here
from common.proc import _pid_alive_windows, pid_alive  # noqa: F401


def _kill_browser_windows(pid: int, grace: float) -> bool:
    """Clean up child renderers too with taskkill /T. Graceful first, /F if it does not die."""
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
    """Clean up the browser directly. Wait for graceful exit and force-kill if it does not die. True if still alive.

    Attaching over CDP and calling close() hangs without limit on an unresponsive browser (#712).
    It was launched as a separate process, so ending it by signal is more reliable.
    """
    if sys.platform == "win32":
        return _kill_browser_windows(pid, grace)
    # Graceful signal only to the main process — sending to the whole group ends it before cookies·sign-in are written to disk (observed, #956)
    # If it does not die, force-kill the whole group (launched in a new session, so pid is also the process group id)
    for sig, wait, is_group in ((signal.SIGTERM, grace, False), (signal.SIGKILL, 3.0, True)):
        _send_signal(pid, sig, is_group)
        end = time.time() + wait
        while time.time() < end:
            if not pid_alive(pid):
                if not is_group:
                    _send_signal(pid, signal.SIGKILL, True)   # clean up remaining renderers
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
    """Popen options that keep the browser alive after we exit (the equivalent of a new POSIX session)."""
    if sys.platform == "win32":
        return {"creationflags": 0x00000008 | 0x00000200}   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    return {"start_new_session": True}


def process_command_lines() -> str | None:
    """Command lines of all running processes as one blob. None if unreadable.

    Windows has no ps, and command lines with Korean paths fail to decode with the default code page,
    making stdout None — so the encoding is explicit.
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
    """Command for the user to end the browser themselves."""
    return f"taskkill /PID {pid} /T /F" if sys.platform == "win32" else f"kill -9 {pid}"


def spawn_detached(command: list[str], working_folder: str, log_path, is_stdout_logged: bool = False) -> int:
    """Start a background process that outlives us > pid. stderr goes to log_path (overwritten).

    is_stdout_logged: stdout to the same log too (the emulator writes even errors to stdout, #987)
    """
    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                   stdout=log_file if is_stdout_logged else subprocess.DEVNULL,
                                   stderr=log_file, cwd=working_folder, **detach_options())
    return process.pid


def interrupt_process(pid: int, wait_seconds: float = 10.0) -> bool:
    """Send SIGINT so it finishes on its own (to close the recording file). True if ended. Windows uses a graceful close request instead."""
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
    """End a process started in a new session together with its children (e.g. relay > maestro mcp > java). True if still alive."""
    return kill_browser(pid, grace)


def elapsed_seconds_from_ps(etime: str) -> int | None:
    """ps etime ([[days-]hours:]minutes:seconds) > seconds. None if unreadable."""
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
    """Running process list > [{pid, ppid, elapsed_seconds, command}]. None if unreadable.

    elapsed_seconds: seconds since start (None if unreadable) — grounds for not cleaning up just-started ones
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
    """One process > {pid, ppid, elapsed_seconds, command}. None if missing or unreadable (faster than the full list)."""
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
    """Try an exclusive lock on an open file (no waiting). macOS·Linux flock · Windows msvcrt (device ledger, #953)."""
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
        pass   # the OS releases the lock when the file closes


def clone_tree(source: str, target: str) -> tuple[bool, str]:
    """Clone a folder > (success, error). macOS APFS clone (cp -c, shared blocks) · Linux reflink when possible · otherwise a plain copy (#959)."""
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
        result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=600)
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    return result.returncode == 0, (result.stderr or "").strip()[-300:]


def read_windows_memory() -> dict | None:
    """Windows memory > {total_mb, available_mb, swap_total_mb, swap_used_mb}. None when not Windows (#964).

    GlobalMemoryStatusEx — the part of the page file (commit) beyond physical memory is treated as swap.
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
    """Sum of resident memory of the processes (MB). Unreadable ones count 0 — for measuring device cost (#964)."""
    if not pids:
        return 0
    try:
        if sys.platform == "win32":
            pid_list = ",".join(str(pid) for pid in pids)
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                f"(Get-Process -Id {pid_list} -ErrorAction SilentlyContinue | "
                                "Measure-Object WorkingSet64 -Sum).Sum"],
                               capture_output=True, text=True, errors="replace", timeout=15)
            total_bytes = int(float((r.stdout or "0").strip() or 0))
            return total_bytes // (1024 * 1024)
        if sys.platform == "darwin":
            # RSS drops a lot by excluding compressed·swapped parts (observed: emulator RSS 245MB, top MEM 5.6GB) — top footprint
            command = ["top", "-l", "1", "-stats", "pid,mem"]
            for pid in pids:
                command += ["-pid", str(pid)]
            r = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=20)
            return sum(_size_to_mb(fields[1]) for fields in (line.split() for line in (r.stdout or "").splitlines())
                       if len(fields) == 2 and fields[0].isdigit() and int(fields[0]) in pids)
        r = subprocess.run(["ps", "-o", "rss=", "-p", ",".join(str(pid) for pid in pids)],
                           capture_output=True, text=True, errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0
    return sum(int(line) for line in (r.stdout or "").split() if line.isdigit()) // 1024


def _size_to_mb(text: str) -> int:
    """top size notation (512K · 5611M · 1.2G, trailing +/- ignored) > MB."""
    match = re.match(r"^([\d.]+)([KMGT]?)", text.rstrip("+-"))
    if not match:
        return 0
    scale = {"": 1 / (1024 * 1024), "K": 1 / 1024, "M": 1, "G": 1024, "T": 1024 * 1024}[match.group(2)]
    return int(float(match.group(1)) * scale)


def top_memory_processes(count: int) -> list[dict]:
    """Processes using the most memory > [{pid, name, memory_mb}] (#964).

    macOS uses top footprint (includes compressed·swap — RSS makes VMs·emulators look much smaller), Windows WorkingSet, others RSS.
    """
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["top", "-l", "1", "-o", "mem", "-n", str(count), "-stats", "pid,mem,command"],
                               capture_output=True, text=True, errors="replace", timeout=20)
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
                               capture_output=True, text=True, errors="replace", timeout=20)
        else:
            r = subprocess.run(["ps", "-axo", "pid=,rss=,comm=", "--sort=-rss"], capture_output=True, text=True, errors="replace", timeout=10)
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
    """pids of processes whose command line contains text (e.g. a simulator UDID — that device's process group). Our own processes excluded."""
    rows = process_table() or []
    return [row["pid"] for row in rows if text in (row.get("command") or "") and row["pid"] != os.getpid()]


# Clipboard read commands — per OS, the first one available from the top
_CLIPBOARD_COMMANDS = {
    "darwin": (["pbpaste"],),
    "win32": (["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],),
    "linux": (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"],
              ["xsel", "--clipboard", "--output"]),
}


def read_system_clipboard() -> tuple[str | None, str | None]:
    """Host clipboard text > (value, failure reason). macOS pbpaste · Windows Get-Clipboard · Linux wl-paste/xclip/xsel."""
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
    """pids of processes whose command line has arguments adjacent in this order (e.g. "-avd", "Pixel" — partial name matches excluded).

    Empty list if unreadable. Our own processes excluded.
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
    """End immediately without a graceful exit (emulator qemu that ignores emu kill). True if still alive."""
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
