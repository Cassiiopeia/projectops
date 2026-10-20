"""device acquire · release · shutdown (#953) — 가짜 백엔드로 기기 없이 검사한다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.device import acquire, claims, pool  # noqa: E402
from pro_launch.runtime import device_backends, device_claims, device_pool_facts  # noqa: E402
from pro_launch.runtime.device_backends.base import Capabilities, DeviceFacts  # noqa: E402


class FakeBackend:
    name = "fake_ios"
    platform = "ios"
    capabilities = Capabilities(can_boot=True, can_shutdown=True)

    def __init__(self, booted=()):
        self.booted = set(booted)
        self.calls = []

    def list_devices(self):
        return [DeviceFacts(key=k, platform="ios", backend=self.name, name=f"phone-{k}", form="phone",
                            os_version="18.3", is_booted=k in self.booted, instance=k if k in self.booted else None)
                for k in ("A", "B")]

    def boot(self, key, window, scale):
        self.calls.append(("boot", key))
        self.booted.add(key)
        return {"is_ok": True, "instance": key, "already_booted": False, "detail": None}

    def shutdown(self, key, instance):
        self.calls.append(("shutdown", key))
        self.booted.discard(key)
        return {"is_ok": True, "detail": None}

    def key_of_instance(self, instance):
        return instance


@pytest.fixture
def backend(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(device_backends, "BACKENDS", (fake,))
    monkeypatch.setattr(device_pool_facts.host_resources, "memory_summary", lambda: {"pressure": "ok"})
    monkeypatch.setattr(device_pool_facts, "disk_status",
                        lambda path=None: {"free_gb": 100.0, "minimum_gb": 20, "is_low": False})
    monkeypatch.setattr(device_pool_facts, "max_booted_limit", lambda: (4, "default"))
    monkeypatch.setattr(device_claims, "current_host", lambda: None)
    # resolve_device 가 실제 adb·simctl 을 보지 않게 — 지정한 기기를 그대로 쓴다
    monkeypatch.setattr(claims, "pick_device", lambda want: ("ios", want, {}))
    monkeypatch.setattr(acquire.time, "sleep", lambda seconds: None)
    return fake


def args(tmp_path, **values):
    base = dict(root=str(tmp_path), platform="ios", form=None, os=None, device=None, purpose="#953", wait=0,
                window=None, scale=None, yes=False, lease=None, all=False, keep_booted=False, need=None, fresh=False,
                count=1, reason=None, name=None, ttl_days=None, kind=None, note=None, verify=False)
    base.update(values)
    return argparse.Namespace(**base)


def result_of(capsys):
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_acquire_boots_shutdown_device_and_records_booted_by_lease(monkeypatch, tmp_path, capsys, backend):
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    acquire.run_acquire(args(tmp_path))
    data = result_of(capsys)
    assert data["verdict"] == "reuse" and data["booted"] is True and data["lease_id"]
    assert ("boot", data["device"]) in backend.calls
    assert device_claims.device_owner(data["device"])["is_booted_by_lease"] is True


def test_second_session_gets_the_other_device(monkeypatch, tmp_path, capsys, backend):
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    acquire.run_acquire(args(tmp_path))
    first = result_of(capsys)["device"]
    monkeypatch.setenv("LAUNCH_SESSION", "s2")
    acquire.run_acquire(args(tmp_path))
    assert result_of(capsys)["device"] != first


def test_acquire_wait_accumulates_across_calls_then_asks(monkeypatch, tmp_path, capsys, backend):
    for session in ("s1", "s2"):
        monkeypatch.setenv("LAUNCH_SESSION", session)
        acquire.run_acquire(args(tmp_path))
        result_of(capsys)
    monkeypatch.setenv("LAUNCH_SESSION", "s3")
    acquire.run_acquire(args(tmp_path))
    busy = result_of(capsys)
    assert busy["code"] == "device_busy" and len(busy["owners"]) == 2
    wait_key = acquire.wait_key(acquire.AcquireRequest(platform="ios", form="phone", purpose="#953"))
    monkeypatch.setattr(device_claims, "waited_seconds", lambda key: 601 if key == wait_key else 0)
    acquire.run_acquire(args(tmp_path))
    assert result_of(capsys)["code"] == "needs_user"


def test_release_shuts_down_only_what_this_lease_booted(monkeypatch, tmp_path, capsys, backend):
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    backend.booted.add("A")
    device_claims.set_pool_booted("A", True)   # 원장이 켠 기기라 후보가 된다
    acquire.run_acquire(args(tmp_path, device="A"))
    result_of(capsys)
    pool.run_release(args(tmp_path, device="A"))
    data = result_of(capsys)
    assert data["released"] is True
    acquire.run_acquire(args(tmp_path))
    booted_device = result_of(capsys)["device"]
    pool.run_release(args(tmp_path, device=booted_device))
    assert result_of(capsys)["shutdown"] is True and ("shutdown", booted_device) in backend.calls


def test_release_does_not_shutdown_when_another_lease_remains(monkeypatch, tmp_path, capsys, backend):
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    acquire.run_acquire(args(tmp_path))
    device = result_of(capsys)["device"]
    # 같은 기기에 다른 세션 lease 가 하나 더 있다 (예: --yes 로 함께 쓰는 중)
    monkeypatch.setattr(device_claims, "release_device",
                        lambda dev_id, lease_id=None: {"owner": {"key": device}, "settings": [],
                                                       "lease": {"is_booted_by_lease": True, "backend": "fake_ios",
                                                                 "instance": device},
                                                       "remaining_live_leases": 1})
    pool.run_release(args(tmp_path, device=device))
    data = result_of(capsys)
    assert data["shutdown"] is False and data["shutdown_reason"] == "another_lease"


def test_release_all_releases_every_lease_of_session(monkeypatch, tmp_path, capsys, backend):
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    for _ in range(2):
        acquire.run_acquire(args(tmp_path))
        result_of(capsys)
    pool.run_release(args(tmp_path, all=True))
    data = result_of(capsys)
    assert len(data["released"]) == 2 and all(row["shutdown"] for row in data["released"])
    assert device_claims.leases_of_session("s1") == []


def test_keep_booted_release_keeps_device_as_pool_candidate(monkeypatch, tmp_path, capsys, backend):
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    acquire.run_acquire(args(tmp_path))
    device = result_of(capsys)["device"]
    pool.run_release(args(tmp_path, device=device, keep_booted=True))
    assert result_of(capsys)["shutdown_reason"] == "keep_booted"
    monkeypatch.setenv("LAUNCH_SESSION", "s2")
    acquire.run_acquire(args(tmp_path))
    data = result_of(capsys)
    assert data["device"] == device and data["booted"] is False


def test_shutdown_refuses_other_live_lease_without_yes(monkeypatch, tmp_path, capsys, backend):
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    acquire.run_acquire(args(tmp_path))
    device = result_of(capsys)["device"]
    monkeypatch.setenv("LAUNCH_SESSION", "s2")
    pool.run_shutdown(args(tmp_path, device=device))
    assert result_of(capsys)["code"] == "device_owned_by_other"
    pool.run_shutdown(args(tmp_path, device=device, yes=True))
    assert result_of(capsys)["action"] == "shutdown"


def test_reclaim_restores_dead_session_settings_and_reports_failures(monkeypatch, tmp_path, capsys, backend):
    monkeypatch.setenv("LAUNCH_SESSION", "dead")
    acquire.run_acquire(args(tmp_path, device="A"))
    result_of(capsys)
    device_claims.record_device_setting("A", "appearance", "light", [["restore-appearance"]])
    device_claims.record_device_setting("A", "locale:system", "ko", [["restore-locale"]])
    monkeypatch.setattr(device_claims, "is_lease_live", lambda lease, now=None, probe=None: lease.get("session") != "dead")
    monkeypatch.setattr(acquire, "run_restore_commands",
                        lambda setting: {"is_ok": setting["key"] == "appearance", "key": setting["key"]})
    monkeypatch.setenv("LAUNCH_SESSION", "s2")
    acquire.run_acquire(args(tmp_path, device="A"))
    data = result_of(capsys)
    assert data["verdict"] == "reclaim"
    assert [s["key"] for s in data["unrestored_settings"]] == ["locale:system"]
    assert device_claims.device_owner("A")["changed_settings"] == ["locale:system"]


def test_acquire_without_platform_is_rejected(tmp_path, capsys, backend):
    acquire.run_acquire(args(tmp_path, platform=None))
    assert result_of(capsys)["code"] == "args_required"
