"""device gc (#955) — 지울 것은 기한 지난 임시 기기뿐, 기록 없는·공들인 기기는 보고만."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.device import gc  # noqa: E402
from pro_launch.runtime import device_backends, device_claims, device_gc, device_ledger, device_marks  # noqa: E402
from pro_launch.runtime.device_backends.base import Capabilities, DeviceFacts  # noqa: E402

GB = 1024 ** 3


class GcBackend:
    name = "fake_ios"
    platform = "ios"
    capabilities = Capabilities(can_boot=True, can_shutdown=True, can_create=True)

    def __init__(self, keys, booted=()):
        self.keys, self.booted, self.calls = list(keys), set(booted), []
        self.unavailable = []

    def list_devices(self):
        return [DeviceFacts(key=k, platform="ios", backend=self.name, name=f"dev-{k}", form="phone", os_version="18.3",
                            is_booted=k in self.booted, instance=k if k in self.booted else None) for k in self.keys]

    def delete(self, key):
        self.calls.append(("delete", key))
        self.keys.remove(key)
        return {"is_ok": True, "detail": None}

    def disk_bytes(self, key):
        self.calls.append(("size", key))
        return 2 * GB

    def unavailable_devices(self):
        return self.unavailable


@pytest.fixture
def setup(monkeypatch):
    def install(keys, booted=()):
        backend = GcBackend(keys, booted)
        monkeypatch.setattr(device_backends, "BACKENDS", (backend,))
        monkeypatch.setattr(device_claims, "current_host", lambda: None)
        return backend
    return install


def gc_args(**values):
    return argparse.Namespace(**{"apply": False, "sizes": False, **values})


def result_of(capsys):
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def expire(key):
    def mutate(ledger):
        ledger["devices"][key]["temporary"]["expires_at"] = time.time() - 1
    device_ledger.update_ledger(mutate)


def actions_by_key(plan):
    return {row["key"]: row["action"] for row in plan.rows}


def test_only_expired_unleased_unmarked_temporary_is_deleted(setup):
    setup(["OLD", "MARKED", "FRESH", "HUMAN"])
    for key in ("OLD", "MARKED", "FRESH"):
        device_marks.record_created(key, "#955 테스트", 3, "fake_ios")
    expire("OLD")
    expire("MARKED")
    device_marks.add_mark("MARKED", "login", "kakao")
    plan = device_gc.build_plan()
    assert actions_by_key(plan) == {"OLD": "delete", "MARKED": "keep", "FRESH": "keep", "HUMAN": "keep"}
    reasons = {row["key"]: row["reason"] for row in plan.rows}
    assert "marked state" in reasons["MARKED"] and "not in the ledger" in reasons["HUMAN"]


def test_report_changes_nothing_and_apply_deletes_and_forgets(setup, capsys):
    backend = setup(["OLD", "HUMAN"])
    device_marks.record_created("OLD", "x", 3, "fake_ios")
    expire("OLD")
    gc.run_gc(gc_args())
    report = result_of(capsys)
    assert report["applied"] is False and report["reclaimable_gb"] == 2.0 and backend.keys == ["OLD", "HUMAN"]
    gc.run_gc(gc_args(apply=True))
    applied = result_of(capsys)
    assert applied["freed_gb"] == 2.0 and backend.keys == ["HUMAN"]
    assert "OLD" not in device_marks.record_views()


