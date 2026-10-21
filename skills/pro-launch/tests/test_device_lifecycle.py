"""device delete · mark · clone 보호 규칙 (#954) — 가짜 백엔드."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.device import claims, lifecycle  # noqa: E402
from pro_launch.runtime import device_backends, device_claims, device_marks, device_pool_facts  # noqa: E402
from pro_launch.runtime.device_backends.base import Capabilities, DeviceFacts  # noqa: E402


class CreatingBackend:
    name = "fake_ios"
    platform = "ios"
    capabilities = Capabilities(can_boot=True, can_shutdown=True, can_create=True, can_clone=True,
                                can_clone_keep_marks=True)

    def __init__(self):
        self.keys, self.booted, self.calls = ["A"], set(), []

    def list_devices(self):
        return [DeviceFacts(key=k, platform="ios", backend=self.name, name=f"phone-{k}", form="phone", os_version="18.3",
                            is_booted=k in self.booted, instance=k if k in self.booted else None) for k in self.keys]

    def shutdown(self, key, instance):
        self.booted.discard(key)
        return {"is_ok": True, "detail": None}

    def key_of_instance(self, instance):
        return instance

    def delete(self, key):
        self.keys.remove(key)
        self.calls.append(("delete", key))
        return {"is_ok": True, "detail": None}


@pytest.fixture
def backend(monkeypatch):
    fake = CreatingBackend()
    monkeypatch.setattr(device_backends, "BACKENDS", (fake,))
    monkeypatch.setattr(device_pool_facts.host_resources, "read_memory", lambda: {"total_mb": 16384, "available_mb": 12000, "swap_total_mb": 0, "swap_used_mb": 0, "os_pressure": "ok"})
    monkeypatch.setattr(device_pool_facts, "disk_status",
                        lambda path=None: {"free_gb": 100.0, "minimum_gb": 20, "is_low": False})
    monkeypatch.setattr(device_pool_facts.device_capacity, "boot_block_reason", lambda platform, counts, memory=None: None)
    monkeypatch.setattr(device_claims, "current_host", lambda: None)
    monkeypatch.setattr(claims, "pick_device", lambda want: ("ios", want, {}))
    monkeypatch.setenv("LAUNCH_SESSION", "s1")
    return fake


def args(tmp_path, **values):
    base = dict(root=str(tmp_path), platform="ios", form=None, os=None, device=None, purpose="#954", wait=0,
                window=None, scale=None, yes=False, lease=None, all=False, keep_booted=False, need=None, fresh=False,
                count=1, reason=None, name=None, ttl_days=None, kind=None, note=None, verify=False)
    base.update(values)
    return argparse.Namespace(**base)


def result_of(capsys):
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_mark_protects_device_from_delete_until_yes(tmp_path, capsys, backend):
    lifecycle.run_mark(args(tmp_path, device="A", kind="login", name="kakao", note="guardian"))
    assert result_of(capsys)["mark"]["name"] == "kakao"
    lifecycle.run_delete(args(tmp_path, device="A"))
    refused = result_of(capsys)
    assert refused["code"] == "device_protected" and refused["marks"][0]["label"] == "login:kakao"
    lifecycle.run_delete(args(tmp_path, device="A", yes=True))
    assert result_of(capsys)["action"] == "delete" and ("delete", "A") in backend.calls
    assert "A" not in device_marks.record_views()


def test_delete_refuses_human_booted_unrecorded_device(tmp_path, capsys, backend):
    backend.booted.add("A")
    lifecycle.run_delete(args(tmp_path, device="A"))
    assert result_of(capsys)["code"] == "device_in_use_unrecorded"


def test_clone_refuses_booted_source(tmp_path, capsys, backend):
    backend.booted.add("A")
    lifecycle.run_clone(args(tmp_path, device="A", reason="x"))
    assert result_of(capsys)["code"] == "source_booted"


