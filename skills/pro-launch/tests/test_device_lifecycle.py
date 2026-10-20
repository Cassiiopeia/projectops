"""device create · erase · delete · mark · adopt · records · acquire --need/--fresh/--count (#954) — 가짜 백엔드."""
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

from pro_launch.commands.device import acquire, claims, lifecycle  # noqa: E402
from pro_launch.runtime import device_backends, device_claims, device_marks, device_pool_facts  # noqa: E402
from pro_launch.runtime.device_backends.base import Capabilities, DeviceFacts  # noqa: E402


class CreatingBackend:
    name = "fake_ios"
    platform = "ios"
    capabilities = Capabilities(can_boot=True, can_shutdown=True, can_create=True)

    def __init__(self):
        self.keys, self.booted, self.calls = ["A"], set(), []

    def list_devices(self):
        return [DeviceFacts(key=k, platform="ios", backend=self.name, name=f"phone-{k}", form="phone", os_version="18.3",
                            is_booted=k in self.booted, instance=k if k in self.booted else None) for k in self.keys]

    def boot(self, key, window, scale):
        self.booted.add(key)
        return {"is_ok": True, "instance": key, "already_booted": False, "detail": None}

    def shutdown(self, key, instance):
        self.booted.discard(key)
        return {"is_ok": True, "detail": None}

    def key_of_instance(self, instance):
        return instance

    def create(self, name, form, os_minimum):
        key = f"NEW{len(self.keys)}"
        self.keys.append(key)
        self.calls.append(("create", name))
        return {"is_ok": True, "key": key, "detail": None}

    def erase(self, key):
        self.calls.append(("erase", key))
        return {"is_ok": True, "detail": None}

    def delete(self, key):
        self.keys.remove(key)
        self.calls.append(("delete", key))
        return {"is_ok": True, "detail": None}

    def raw_command_patterns(self):
        return ()


@pytest.fixture
def backend(monkeypatch):
    fake = CreatingBackend()
    monkeypatch.setattr(device_backends, "BACKENDS", (fake,))
    monkeypatch.setattr(device_pool_facts.host_resources, "memory_summary", lambda: {"pressure": "ok"})
    monkeypatch.setattr(lifecycle.host_resources, "memory_summary", lambda: {"pressure": "ok"})
    monkeypatch.setattr(device_pool_facts, "disk_status",
                        lambda path=None: {"free_gb": 100.0, "free_ratio": 0.5, "minimum_gb": 20, "is_low": False})
    monkeypatch.setattr(device_pool_facts, "max_booted_limit", lambda: (4, "default"))
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


def test_acquire_need_uses_marked_device_and_tells_how_when_missing(tmp_path, capsys, backend):
    acquire.run_acquire(args(tmp_path, need=["login:kakao"]))
    missing = result_of(capsys)
    assert missing["code"] == "no_matching_device" and "device mark" in missing["next"]
    device_marks.add_mark("A", "login", "kakao")
    acquire.run_acquire(args(tmp_path, need=["login:kakao"]))
    assert result_of(capsys)["device"] == "A"


def test_fresh_creates_temporary_device_with_reason_and_consumes_pristine(tmp_path, capsys, backend):
    acquire.run_acquire(args(tmp_path, fresh=True, reason="#954 완전 새 폰"))
    data = result_of(capsys)
    assert data["verdict"] == "create" and data["created"] is True and data["booted"] is True
    record = device_marks.record_views()[data["key"]]
    assert record["origin"] == "recorded" and record["temporary"]["reason"] == "#954 완전 새 폰"
    assert record["is_pristine"] is False   # 빌린 순간 새 폰이 아니다


def test_count_takes_distinct_devices_creating_the_missing_one(tmp_path, capsys, backend):
    acquire.run_acquire(args(tmp_path, count=2))
    data = result_of(capsys)
    assert data["ok"] is True and len(set(data["devices"])) == 2
    assert [call for call in backend.calls if call[0] == "create"]


def test_create_command_needs_reason_and_respects_low_disk(monkeypatch, tmp_path, capsys, backend):
    lifecycle.run_create(args(tmp_path))
    assert result_of(capsys)["code"] == "args_required"
    monkeypatch.setattr(device_pool_facts, "disk_status",
                        lambda path=None: {"free_gb": 5.0, "free_ratio": 0.02, "minimum_gb": 20, "is_low": True})
    lifecycle.run_create(args(tmp_path, reason="두 대 테스트"))
    assert result_of(capsys)["code"] == "resources_low"
    lifecycle.run_create(args(tmp_path, reason="두 대 테스트", yes=True, ttl_days=1))
    created = result_of(capsys)
    assert created["action"] == "create"
    assert created["temporary"]["expires_at"] - created["temporary"]["created_at"] == pytest.approx(86400)


def test_erase_clears_marks_and_makes_device_pristine(tmp_path, capsys, backend):
    device_marks.add_mark("A", "data", "seed")
    lifecycle.run_erase(args(tmp_path, device="A", yes=True))
    assert result_of(capsys)["action"] == "erase"
    record = device_marks.record_views()["A"]
    assert record["marks"] == [] and record["is_pristine"] is True


def test_delete_refuses_human_booted_unrecorded_device(tmp_path, capsys, backend):
    backend.booted.add("A")
    lifecycle.run_delete(args(tmp_path, device="A"))
    assert result_of(capsys)["code"] == "device_in_use_unrecorded"


def test_mark_verify_and_stale_detection(monkeypatch, tmp_path, capsys, backend):
    device_marks.add_mark("A", "login", "naver")
    monkeypatch.setattr(device_marks, "mark_stale_seconds", lambda: 0.0)
    time.sleep(0.01)
    assert device_marks.record_views()["A"]["marks"][0]["is_stale"] is True
    lifecycle.run_mark(args(tmp_path, device="A", kind="login", name="naver", verify=True))
    assert result_of(capsys)["mark"]["verified_at"] > 0
    lifecycle.run_mark(args(tmp_path, device="A", kind="login", name="nope", verify=True))
    assert result_of(capsys)["code"] == "mark_not_found"


def test_records_and_adopt(tmp_path, capsys, backend):
    lifecycle.run_records(args(tmp_path))
    assert result_of(capsys)["devices"][0]["origin"] == "unrecorded"
    lifecycle.run_adopt(args(tmp_path, device="phone-A"))
    assert result_of(capsys)["origin"] == "adopted"
    lifecycle.run_records(args(tmp_path))
    assert result_of(capsys)["devices"][0]["origin"] == "adopted"


def test_unknown_device_name_is_reported(tmp_path, capsys, backend):
    lifecycle.run_mark(args(tmp_path, device="nothing", kind="login", name="x"))
    assert result_of(capsys)["code"] == "no_device"
