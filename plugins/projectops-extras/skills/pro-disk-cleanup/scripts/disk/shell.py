"""External command runner: fixed encoding, time limit, absorbs missing commands"""
from __future__ import annotations

import shutil
import subprocess
import sys

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# Default time limit per command (seconds)
DEFAULT_TIMEOUT_SECONDS = 120


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def run(arguments: list[str], cwd: str | None = None, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> tuple[int, str, str]:
    """Run command > (exit code, stdout, stderr). Missing command and timeout give 127 and 124"""
    try:
        completed = subprocess.run(arguments, cwd=cwd, capture_output=True, encoding="utf-8",
                                   errors="replace", timeout=timeout_seconds)
    except FileNotFoundError:
        return 127, "", f"command not found: {arguments[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout_seconds}s: {' '.join(arguments[:3])}"
    except OSError as error:
        return 126, "", str(error)
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def git(worktree_path: str, *arguments: str, timeout_seconds: int = 60) -> tuple[int, str]:
    """git -C path ... > (exit code, stdout stripped)"""
    code, out, _ = run(["git", "-C", worktree_path, *arguments], timeout_seconds=timeout_seconds)
    return code, out.strip()
