"""기기 켜기 차례: 이 컴퓨터 전체에서 한 번에 한 세션만 가상 기기를 켠다 (#964).

세션들이 각자 "켜도 된다"고 판단해 동시에 켜면 함께 한도를 넘어 다 같이 멈춘다.
차례를 얻은 쪽이 그 안에서 최신 메모리로 다시 판정하고 켠다 — 앞 세션이 켠 몫이 반영된다.
"""
from __future__ import annotations

import contextlib
import time

from common.state import MACHINE_BUCKET, base_dir

from pro_launch.runtime import procs

BOOT_LOCK_FILE_NAME = "device-boot.lock"
# 차례를 기다리는 상한 (초) — 앞 세션의 부팅(보통 60~120초)을 기다린다
BOOT_TURN_WAIT_SECONDS = 150
BOOT_TURN_RETRY_SECONDS = 1.0


class BootTurnBusyError(RuntimeError):
    """상한 안에 차례를 얻지 못했다 — 다른 세션이 기기를 켜는 중이다."""


@contextlib.contextmanager
def boot_turn(wait_seconds: float = BOOT_TURN_WAIT_SECONDS):
    """켜기 차례 구간. 상한 안에 못 얻으면 BootTurnBusyError."""
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
