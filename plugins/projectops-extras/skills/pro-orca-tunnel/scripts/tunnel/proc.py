"""Run external commands and find Android SDK tools (shared by pro-launch · pro-agent-test, #629).

If both CLIs kept their own copy, only one would get fixed and they would drift. It lives here in one place.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], timeout: int = 15) -> str:
    """Run an external command. Never raises on failure;
    a missing device or uninstalled tool is a normal path."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
        return r.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def sdk_tool(name: str) -> str | None:
    """Path to an Android SDK tool. If not on PATH, check the standard install locations.

    adb and emulator are often not added to PATH even after installing the SDK.
    Without finding them here, a present device would be reported as "missing".
    """
    found = shutil.which(name)
    if found:
        return found

    # Windows executables carry an extension. The same holds in Git Bash.
    exe = f"{name}.exe" if sys.platform == "win32" else name

    roots = [Path.home() / "Library" / "Android" / "sdk",   # macOS default
             Path.home() / "Android" / "Sdk"]               # Linux default
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT", "LOCALAPPDATA"):
        v = os.environ.get(env)
        if not v:
            continue
        base = Path(v)
        roots.append(base / "Android" / "Sdk" if env == "LOCALAPPDATA" else base)

    for root in roots:
        for sub in ("platform-tools", "emulator", "cmdline-tools/latest/bin"):
            cand = root / sub / exe
            if cand.exists():
                return str(cand)
    return None


# bash that must not be used on Windows even if on PATH: System32 is the WSL launcher, WindowsApps is a Store stub
_WINDOWS_FAKE_BASH_FOLDERS = ("\\windows\\system32", "\\windowsapps")
# Standard install locations to check when Git is not on PATH
_WINDOWS_GIT_BASH_PATHS = (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe")


def bash_executable() -> str:
    """bash for running shell commands. On Windows, return the full path; CreateProcess checks System32 (WSL launcher) before PATH"""
    if sys.platform != "win32":
        return "bash"
    folders = [folder for folder in os.environ.get("PATH", "").split(os.pathsep)
               if not any(fake in folder.lower().rstrip("\\") + "\\" or folder.lower().rstrip("\\").endswith(fake)
                          for fake in _WINDOWS_FAKE_BASH_FOLDERS)]
    found = shutil.which("bash", path=os.pathsep.join(folders))
    if found:
        return found
    return next((path for path in _WINDOWS_GIT_BASH_PATHS if Path(path).is_file()), "bash")


def pid_alive(pid) -> bool:
    """Check whether a process is alive (single OS-branch point). Reaps our own zombie children and reports them dead"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    # On Windows, os.kill(pid, 0) terminates instead of checking
    if sys.platform == "win32":
        return _pid_alive_windows(pid)
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)
        if done:
            return False
    except OSError:  # Not our child (ChildProcessError included); decide by the signal check below
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _pid_alive_windows(pid: int) -> bool:
    """Open a handle and check the exit code (alive if STILL_ACTIVE)"""
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
