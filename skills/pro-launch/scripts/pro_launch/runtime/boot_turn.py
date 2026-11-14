"""Device boot turn: only one session on this whole computer boots a virtual device at a time (#964).

If sessions each decide "OK to boot" and boot together, they exceed the limit together and all stall.
The holder of the turn re-checks with fresh memory figures inside it and boots — the share booted by the previous session is accounted for.
"""
from __future__ import annotations

import contextlib
import time

from common.state import MACHINE_BUCKET, base_dir

from pro_launch.runtime import procs

BOOT_LOCK_FILE_NAME = "device-boot.lock"
# Cap for waiting for the turn (s) — waits out the previous session's boot (usually 60-120 s)
BOOT_TURN_WAIT_SECONDS = 150
BOOT_TURN_RETRY_SECONDS = 1.0


class BootTurnBusyError(RuntimeError):
    """Could not get the turn within the cap — another session is booting a device."""


@contextlib.contextmanager
def boot_turn(wait_seconds: float = BOOT_TURN_WAIT_SECONDS):
    """Boot turn section. BootTurnBusyError if not acquired within the cap."""
    path = base_dir() / "launch" / MACHINE_BUCKET / BOOT_LOCK_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as handle:
        deadline = time.monotonic() + wait_seconds
        while not procs.try_lock_file(handle):
            if time.monotonic() >= deadline:
                raise BootTurnBusyError(f"another session is booting a device ({wait_seconds:.0f}s)")
            time.sleep(BOOT_TURN_RETRY_SECONDS)
        try:
            yield
        finally:
            procs.unlock_file(handle)
