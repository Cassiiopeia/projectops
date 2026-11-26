"""Short-lived secret file: hand a stored secret to another tool without putting it in a reply (#1239).

A CLI reply lands in the agent's transcript, so the reply carries only the file path. The consumer reads the file and deletes it.
Files nobody read are removed three ways: by the consumer > by a detached timer after SECRET_FILE_VALID_SECONDS > by the sweep at the next hand-over.
Location: {state root}/launch/_machine/secret-handoff/<random>.secret (under the user's home, never a shared temp folder).
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from common.state import MACHINE_BUCKET, base_dir

from pro_launch.runtime.procs import detach_options

SECRET_HANDOFF_FOLDER = "secret-handoff"
SECRET_FILE_SUFFIX = ".secret"
# How long an unread secret file may stay on disk (10 minutes: longer than one sign-in, short enough to bound exposure)
SECRET_FILE_VALID_SECONDS = 600
# POSIX: owner only. Windows ignores these bits; there the folder inherits the user profile's ACL (owner, SYSTEM, Administrators)
FOLDER_MODE = 0o700
FILE_MODE = 0o600
# Runs detached after this process exits; arguments: file path, seconds
_REMOVAL_TIMER_CODE = (
    "import os, sys, time\n"
    "time.sleep(float(sys.argv[2]))\n"
    "try:\n"
    "    os.unlink(sys.argv[1])\n"
    "except OSError:\n"
    "    pass\n"
)


def secret_handoff_folder() -> Path:
    return base_dir() / "launch" / MACHINE_BUCKET / SECRET_HANDOFF_FOLDER


def remove_expired_secret_files(now: float | None = None) -> int:
    """Delete secret files older than the valid time > how many were removed. Covers a timer that never ran (reboot, kill)."""
    folder = secret_handoff_folder()
    if not folder.is_dir():
        return 0
    deadline = (now if now is not None else time.time()) - SECRET_FILE_VALID_SECONDS
    removed = 0
    for secret_file in folder.glob(f"*{SECRET_FILE_SUFFIX}"):
        try:
            if secret_file.stat().st_mtime <= deadline:
                secret_file.unlink()
                removed += 1
        except OSError:
            continue  # removed meanwhile by its reader or timer
    return removed


def write_secret_file(secret_value: str, start_removal_timer=None) -> Path:
    """Write the value to a new owner-only file > its path. The value is the whole file content (UTF-8, no newline)."""
    remove_expired_secret_files()
    folder = secret_handoff_folder()
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, FOLDER_MODE)
    secret_file = folder / f"{secrets.token_hex(16)}{SECRET_FILE_SUFFIX}"
    # Owner-only from creation: changing the mode after writing leaves a window where others can read it
    descriptor = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    with os.fdopen(descriptor, "wb") as opened_file:
        opened_file.write(secret_value.encode("utf-8"))
    (start_removal_timer or _start_removal_timer)(secret_file, SECRET_FILE_VALID_SECONDS)
    return secret_file


def _start_removal_timer(secret_file: Path, valid_seconds: int) -> None:
    """Detached process that deletes the file after the valid time. Best effort: the next sweep covers a failed start."""
    try:
        subprocess.Popen([sys.executable, "-c", _REMOVAL_TIMER_CODE, str(secret_file), str(valid_seconds)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         **detach_options())
    except OSError:
        pass
