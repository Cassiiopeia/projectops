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
    monkeypatch.setattr(device_pool_facts.host_resources, "read_memory", lambda: {"total_mb": 16384, "available_mb": 12000, "swap_total_mb": 0, "swap_used_mb": 0, "os_pressure": "ok"})
    monkeypatch.setattr(device_pool_facts, "disk_status",
                        lambda path=None: {"free_gb": 100.0, "minimum_gb": 20, "is_low": False})
    monkeypatch.setattr(device_pool_facts.device_capacity, "boot_block_reason", lambda platform, counts, memory=None: None)
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


def test_second_session_gets_the_other_device(monkeypatch, tmp_path, capsys, backend):
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    acquire.run_acquire(args(tmp_path))
    first = result_of(capsys)["device"]
    monkeypatch.setenv("LAUNCH_SESSION", "s2")
    acquire.run_acquire(args(tmp_path))
    assert result_of(capsys)["device"] != first


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


def test_shutdown_refuses_other_live_lease_without_yes(monkeypatch, tmp_path, capsys, backend):
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    acquire.run_acquire(args(tmp_path))
    device = result_of(capsys)["device"]
    monkeypatch.setenv("LAUNCH_SESSION", "s2")
    pool.run_shutdown(args(tmp_path, device=device))
    assert result_of(capsys)["code"] == "device_owned_by_other"
    pool.run_shutdown(args(tmp_path, device=device, yes=True))
    assert result_of(capsys)["action"] == "shutdown"


