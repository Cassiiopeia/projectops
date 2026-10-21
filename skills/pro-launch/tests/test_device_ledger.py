"""기기 원장 schema 2 · lease 생존 · 잠금 (#953) — 실제 기기·프로세스 없이 검사한다."""
from __future__ import annotations

import json
import multiprocessing
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.runtime import device_claims, device_ledger  # noqa: E402


@pytest.fixture
def host_of(monkeypatch):
    """호스트 판별 · 생존을 가짜로: host_of(pid, is_alive)"""
    def set_host(pid: int | None, is_alive: bool | None = True):
        monkeypatch.setattr(device_claims, "current_host", lambda: {"pid": pid, "started_at": 1.0} if pid else None)
        monkeypatch.setattr(device_claims._HostProbe, "is_alive",
                            lambda self, host: None if not host else is_alive)
    return set_host


def test_corrupt_ledger_reads_as_empty_and_next_write_repairs(monkeypatch, host_of):
    host_of(100)
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    path = device_ledger.ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert device_ledger.read_ledger()["devices"] == {}
    device_claims.claim_device("UDID-1", "/r")
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == 2


def test_lease_dies_immediately_when_host_pid_is_gone(monkeypatch, host_of):
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    host_of(100, is_alive=True)
    device_claims.claim_device("UDID-1", "/r")
    monkeypatch.setenv("LAUNCH_SESSION", "s2")
    assert device_claims.check_device_owner("UDID-1") is not None
    host_of(200, is_alive=False)
    assert device_claims.check_device_owner("UDID-1") is None


def _take_first_free_device(ledger_home: str, session: str, queue) -> None:
    import os
    os.environ["PROJECTOPS_HOME"] = ledger_home
    sys.path.insert(0, str(SCRIPTS))
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    from pro_launch.runtime import device_ledger as ledger_module

    def mutate(ledger):
        free = next(k for k in ("A", "B") if k not in ledger["devices"])
        time.sleep(0.2)   # 두 프로세스가 같은 순간에 읽게 한다
        ledger["devices"][free] = {"leases": [{"session": session, "last_used": time.time()}], "settings": []}
        return free

    queue.put(ledger_module.update_ledger(mutate))


def test_concurrent_acquire_gets_different_devices(tmp_path):
    import os
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    home = os.environ["PROJECTOPS_HOME"]
    workers = [context.Process(target=_take_first_free_device, args=(home, f"s{i}", queue)) for i in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
    assert sorted([queue.get(timeout=5), queue.get(timeout=5)]) == ["A", "B"]


