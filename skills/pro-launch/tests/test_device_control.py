"""기기 소유 계약 (#925 소유 · 전역 설정 기록) — 기기 없이 가짜로 검사한다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.app import launch_check  # noqa: E402
from pro_launch.commands.device import claims  # noqa: E402
from pro_launch.runtime import android_device, device_claims, foreground  # noqa: E402
from pro_launch.runtime import devices as rt_devices  # noqa: E402

IOS_UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"
DEVICES = {"android": ["emulator-5554"], "ios_booted": [f"iPhone 16 [{IOS_UDID}]"],
           "android_avds": [], "adb_path": "/x/adb", "emulator_path": None}


def result_of(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def make_args(tmp_path, **values):
    base = dict(root=str(tmp_path), device="emulator-5554", pkg="com.acme.app", path=None, yes=False,
                restore=False, mode=None, lang=None, region=None, app=None)
    base.update(values)
    return argparse.Namespace(**base)


@pytest.fixture
def no_waiting(monkeypatch):
    monkeypatch.setattr(foreground, "FOREGROUND_WAIT_SECONDS", 0)
    monkeypatch.setattr(foreground, "IOS_SETTLE_SECONDS", 0)
    monkeypatch.setattr(launch_check, "CRASH_REPORT_WAIT_SECONDS", 0)
    monkeypatch.setattr(android_device.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(rt_devices, "list_devices", lambda: DEVICES)



def test_other_session_gets_owner_warning_and_same_session_does_not(monkeypatch):
    monkeypatch.setenv("LAUNCH_SESSION", "session-a")
    device_claims.claim_device("emulator-5554", "/work/a")
    assert device_claims.check_device_owner("emulator-5554") is None
    monkeypatch.setenv("LAUNCH_SESSION", "session-b")
    warning = device_claims.check_device_owner("emulator-5554")
    assert warning["code"] == "device_owned_by_other" and warning["session"] == "session-a"
    # 자동 touch 가 남의 소유를 빼앗지 않는다
    device_claims.touch_device("emulator-5554", "/work/b")
    assert device_claims.device_owner("emulator-5554")["session"] == "session-a"


def test_device_setting_keeps_first_value_and_release_returns_newest_first(monkeypatch):
    monkeypatch.setenv("LAUNCH_SESSION", "session-a")
    device_claims.record_device_setting("emulator-5554", "appearance", "no", [["restore-appearance"]])
    device_claims.record_device_setting("emulator-5554", "appearance", "yes", [["wrong"]])
    device_claims.record_device_setting("emulator-5554", "locale:system", "ko-KR", [["restore-locale"]])
    released = device_claims.release_device("emulator-5554")
    assert [s["key"] for s in released["settings"]] == ["locale:system", "appearance"]
    assert released["settings"][1]["before"] == "no"
    assert device_claims.device_owner("emulator-5554") is None


def test_claim_is_refused_without_yes_when_another_session_holds_the_device(monkeypatch, tmp_path, capsys, no_waiting):
    monkeypatch.setenv("LAUNCH_SESSION", "session-a")
    device_claims.claim_device("emulator-5554", "/work/a")
    monkeypatch.setenv("LAUNCH_SESSION", "session-b")
    claims.run_claim(make_args(tmp_path))
    assert result_of(capsys)["code"] == "device_owned_by_other"
    claims.run_claim(make_args(tmp_path, yes=True))
    assert result_of(capsys)["owner"]["session"] == "session-b"
