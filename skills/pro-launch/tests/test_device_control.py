"""기기 제어 계약 (#923 앞에 나왔나 · #924 설치 복구 · #925 소유 · #929 언어·외관 · 창 모드) — 기기 없이 가짜로 검사한다."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.app import launch_check  # noqa: E402
from pro_launch.commands.app.actions import install, launch  # noqa: E402
from pro_launch.commands.device import claims, settings, text_size  # noqa: E402
from pro_launch.runtime import android_device, crash_reports, device_boot, device_claims, foreground  # noqa: E402
from pro_launch.runtime import devices as rt_devices  # noqa: E402

IOS_UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"
DEVICES = {"android": ["emulator-5554"], "ios_booted": [f"iPhone 16 [{IOS_UDID}]"],
           "android_avds": [], "adb_path": "/x/adb", "emulator_path": None}

FOCUS_OTHER_APP = """  mCurrentFocus=Window{4a1b u0 com.google.android.gms/com.google.android.gms.auth.uiflows.minutemaid.MinuteMaidActivity}
  mFocusedApp=ActivityRecord{9c u0 com.google.android.gms/.auth.uiflows.minutemaid.MinuteMaidActivity t7}
  topResumedActivity=ActivityRecord{9c u0 com.google.android.gms/.auth.uiflows.minutemaid.MinuteMaidActivity t7}
"""
FOCUS_TARGET_APP = """  mCurrentFocus=Window{77 u0 com.acme.app/com.acme.app.MainActivity}
  topResumedActivity=ActivityRecord{12 u0 com.acme.app/.MainActivity t3}
"""


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


# ── #923 앞에 나왔나 ─────────────────────────────────────────────────────


def test_parse_foreground_reads_focus_and_resumed_activity():
    other = foreground.parse_android_foreground(FOCUS_OTHER_APP)
    assert other["package"] == "com.google.android.gms" and other["activity"].endswith("MinuteMaidActivity")
    target = foreground.parse_android_foreground(FOCUS_TARGET_APP)
    assert target["package"] == "com.acme.app" and target["resumed_package"] == "com.acme.app"


def test_launch_reports_not_foreground_when_another_activity_is_on_top(monkeypatch, tmp_path, capsys, no_waiting):
    monkeypatch.setattr(launch, "launch_package", lambda platform, dev, package: (True, "Events injected: 1"))
    monkeypatch.setattr(foreground, "read_android_foreground",
                        lambda serial: foreground.parse_android_foreground(FOCUS_OTHER_APP))
    launch._app_launch(make_args(tmp_path))
    data = result_of(capsys)
    assert data["ok"] is False and data["code"] == "not_foreground"
    assert data["foreground_package"] == "com.google.android.gms"
    assert "MinuteMaidActivity" in data["blocking_activity"]


def test_launch_ok_carries_foreground_package(monkeypatch, tmp_path, capsys, no_waiting):
    monkeypatch.setattr(launch, "launch_package", lambda platform, dev, package: (True, "Events injected: 1"))
    monkeypatch.setattr(foreground, "read_android_foreground",
                        lambda serial: foreground.parse_android_foreground(FOCUS_TARGET_APP))
    launch._app_launch(make_args(tmp_path))
    data = result_of(capsys)
    assert data["ok"] and data["foreground_package"] == "com.acme.app"


def _write_crash_report(folder: Path, bundle_id: str, udid: str) -> Path:
    header = {"app_name": "Runner", "bundleID": bundle_id}
    body = {"procPath": f"/Users/x/Library/Developer/CoreSimulator/Devices/{udid}/data/Runner.app/Runner",
            "captureTime": "2026-10-18 10:50:51 +0900",
            "exception": {"type": "EXC_CRASH", "signal": "SIGABRT"},
            "termination": {"indicator": "Abort trap: 6"},
            "asi": {"CoreFoundation": ["*** Terminating app due to uncaught exception 'GADInvalidInitializationException'"]},
            "lastExceptionBacktrace": [{"symbol": "objc_exception_throw"}, {"symbol": "GADApplicationVerify"}]}
    path = folder / "Runner-2026-10-18-105055.ips"
    path.write_text(json.dumps(header) + "\n" + json.dumps(body), encoding="utf-8")
    return path


def test_ios_launch_reports_app_exited_with_crash_report(monkeypatch, tmp_path, capsys, no_waiting):
    reports = tmp_path / "reports"
    reports.mkdir()
    written = _write_crash_report(reports, "com.acme.app", IOS_UDID)
    monkeypatch.setattr(crash_reports, "DIAGNOSTIC_REPORTS_FOLDER", reports)
    monkeypatch.setattr(launch, "launch_package", lambda platform, dev, package: (True, "com.acme.app: 123"))
    monkeypatch.setattr(foreground, "ios_app_is_running", lambda udid, bundle: False)
    launch._app_launch(make_args(tmp_path, device=IOS_UDID))
    data = result_of(capsys)
    assert data["code"] == "app_exited" and data["crash_report"]["path"] == str(written)
    assert "GADInvalidInitializationException" in data["crash_report"]["exception_line"]


def test_crash_report_of_another_app_or_simulator_is_ignored(monkeypatch, tmp_path):
    _write_crash_report(tmp_path, "com.other.app", IOS_UDID)
    monkeypatch.setattr(crash_reports, "DIAGNOSTIC_REPORTS_FOLDER", tmp_path)
    assert crash_reports.newest_crash_report("com.acme.app", IOS_UDID, 0) is None
    assert crash_reports.newest_crash_report("com.other.app", "11111111-1111-1111-1111-111111111111", 0) is None


# ── #924 설치 ────────────────────────────────────────────────────────────


class ScriptedAdb:
    """android_device.adb 대역 — 명령 끝부분으로 응답을 고르고 호출을 기록한다."""

    def __init__(self, replies):
        self.replies = replies   # [(포함할 토큰들, [AdbResult, ...])]
        self.calls: list[tuple] = []

    def __call__(self, serial, *arguments, timeout):
        self.calls.append(arguments)
        for tokens, queue in self.replies:
            if all(t in arguments for t in tokens):
                return queue.pop(0) if len(queue) > 1 else queue[0]
        return android_device.AdbResult(True, "", False)


def _ok(text=""):
    return android_device.AdbResult(True, text, False)


def test_install_retries_once_after_broken_pipe(monkeypatch, tmp_path, no_waiting):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"x")
    adb = ScriptedAdb([
        (("echo",), [_ok("pro-launch-ping")]),
        (("service",), [_ok("Service package: found")]),
        (("install",), [android_device.AdbResult(False, "cmd: Failure calling service package: Broken pipe (32)", False),
                        _ok("Success")]),
    ])
    monkeypatch.setattr(android_device, "adb", adb)
    result = android_device.install_apk("emulator-5554", apk)
    assert result["is_ok"] and result["retried"] is True
    assert sum(1 for c in adb.calls if "install" in c) == 2


def test_install_on_silent_device_reports_unresponsive_with_host_memory(monkeypatch, tmp_path, capsys, no_waiting):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"x")
    monkeypatch.setattr(android_device, "adb", lambda serial, *a, timeout: android_device.AdbResult(False, "응답 없음 (10초)", True))
    monkeypatch.setattr(android_device.host_resources, "memory_summary",
                        lambda: {"pressure": "critical", "available_percent": 3, "swap_used_percent": 96})
    install._app_install(make_args(tmp_path, path=str(apk)))
    data = result_of(capsys)
    assert data["code"] == "device_unresponsive" and data["resources"]["pressure"] == "critical"
    assert "device reboot" in data["next"] and "--cold" in data["next"]


def test_install_rejects_wrong_build_type_for_platform(monkeypatch, tmp_path, capsys, no_waiting):
    ipa = tmp_path / "Runner.ipa"
    ipa.write_bytes(b"x")
    install._app_install(make_args(tmp_path, path=str(ipa), device=IOS_UDID))
    assert result_of(capsys)["code"] == "install_path_invalid"


# ── #925 소유 · 전역 설정 기록 ───────────────────────────────────────────


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


def test_idle_claim_expires_and_can_be_taken_over(monkeypatch):
    monkeypatch.setenv("LAUNCH_SESSION", "session-a")
    device_claims.claim_device("emulator-5554", "/work/a")
    claims_on_disk = json.loads(device_claims.claims_path().read_text(encoding="utf-8"))
    claims_on_disk["claims"]["emulator-5554"]["last_used"] = time.time() - device_claims.CLAIM_IDLE_EXPIRY_SECONDS - 5
    device_claims.claims_path().write_text(json.dumps(claims_on_disk), encoding="utf-8")
    monkeypatch.setenv("LAUNCH_SESSION", "session-b")
    assert device_claims.check_device_owner("emulator-5554") is None
    device_claims.touch_device("emulator-5554", "/work/b")
    assert device_claims.device_owner("emulator-5554")["session"] == "session-b"


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


# ── #929 외관 · 언어 되돌리기 ────────────────────────────────────────────


def test_appearance_records_original_and_restore_runs_it(monkeypatch, tmp_path, capsys, no_waiting):
    ran: list[list[str]] = []

    def fake_run(command):
        ran.append(command)
        return True, "Night mode: no" if command[-1] == "night" else ""
    monkeypatch.setattr(settings, "_run", fake_run)
    monkeypatch.setattr(settings, "sdk_tool", lambda name: "/x/adb")
    real_run = subprocess.run

    def run_restore(command, **kwargs):
        # 되돌리기 명령(adb)만 가로챈다 — 루트 해석의 git 은 진짜로 보낸다
        if command and command[0] == "/x/adb":
            ran.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        return real_run(command, **kwargs)
    monkeypatch.setattr(claims.subprocess, "run", run_restore)
    settings.run_appearance(make_args(tmp_path, mode="dark"))
    data = result_of(capsys)
    assert data["ok"] and data["before"] == "no" and ran[-1][-1] == "yes"
    settings.run_appearance(make_args(tmp_path, restore=True))
    restored = result_of(capsys)
    assert restored["restored"] is True and ran[-1][-2:] == ["night", "no"]


def test_ios_locale_records_original_languages_for_restore(monkeypatch, tmp_path, capsys, no_waiting):
    reads = {"AppleLanguages": (True, "(\n    \"ko-KR\",\n    en\n)"), "AppleLocale": (True, "ko_KR")}
    writes: list[list[str]] = []

    def fake_run(command):
        if "read" in command:
            return reads[command[-1]]
        writes.append(command)
        return True, ""
    monkeypatch.setattr(settings, "_run", fake_run)
    monkeypatch.setattr(settings.device_boot, "shutdown_ios", lambda udid: (True, ""))
    monkeypatch.setattr(settings.device_boot, "boot_ios", lambda udid, window, scale: {"is_ok": True})
    settings.run_locale(make_args(tmp_path, device=IOS_UDID, lang="en", region="US"))
    data = result_of(capsys)
    assert data["before"] == {"languages": ["ko-KR", "en"], "locale": "ko_KR"} and data["rebooted"] is True
    recorded = device_claims.device_owner(IOS_UDID)
    assert recorded["changed_settings"] == ["locale:system"]


# ── 창 모드 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("window,scale,expected", [
    (None, None, ("headless", None)), (None, 0.5, ("small", 0.5)), ("small", None, ("small", 0.4)),
    ("normal", None, ("normal", None)), ("headless", 0.5, ("headless", None)),
])
def test_window_mode_resolution(window, scale, expected):
    assert device_boot.resolve_window(window, scale) == expected


def test_emulator_command_is_headless_or_scaled_and_cold_skips_snapshot():
    headless = device_boot.emulator_command("emu", "Pixel", "headless", None, True, 5554)
    assert "-no-window" in headless and "-no-snapshot-load" in headless and "-scale" not in headless
    windowed = device_boot.emulator_command("emu", "Pixel", "small", 0.4, False, 5556)
    assert windowed[-2:] == ["-scale", "0.4"] and "-no-window" not in windowed


def test_ios_window_scale_is_written_for_this_udid_only(monkeypatch):
    seen: list[list[str]] = []
    monkeypatch.setattr(device_boot, "_read_simulator_preferences", lambda: {"DevicePreferences": {
        "OTHER-UDID": {"SimulatorWindowGeometry": {"SCREEN-1": {"WindowScale": 1.0}}}}})
    monkeypatch.setattr(device_boot, "_run", lambda command, timeout: seen.append(command) or (True, ""))
    assert device_boot.write_window_scale(IOS_UDID, 0.4)[0] is True
    command = seen[0]
    assert command[:5] == ["defaults", "write", device_boot.SIMULATOR_PREFERENCES_DOMAIN, "DevicePreferences", "-dict-add"]
    assert command[5] == IOS_UDID and "SCREEN-1" in command[6] and "<real>0.4</real>" in command[6]


def test_headless_ios_boot_does_not_open_simulator_app(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(device_boot, "ios_simulators", lambda: [{"udid": IOS_UDID, "state": "Shutdown"}])
    monkeypatch.setattr(device_boot, "is_simulator_app_running", lambda: False)
    monkeypatch.setattr(device_boot, "_run", lambda command, timeout: calls.append(command) or (True, ""))
    result = device_boot.boot_ios(IOS_UDID, "headless", None)
    assert result["is_ok"] and not result["window_opened"]
    assert not any(c[0] == "open" for c in calls)


def test_running_simulator_app_is_reported_pending_not_restarted(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(device_boot, "ios_simulators", lambda: [{"udid": IOS_UDID, "state": "Shutdown"}])
    monkeypatch.setattr(device_boot, "is_simulator_app_running", lambda: True)
    monkeypatch.setattr(device_boot, "write_window_scale", lambda udid, scale: (True, ""))
    monkeypatch.setattr(device_boot, "_run", lambda command, timeout: calls.append(command) or (True, ""))
    result = device_boot.boot_ios(IOS_UDID, "small", 0.4)
    assert result["window_scale_pending"] is True and "Window" in result["window_hint"]
    assert not any(c[0] in ("open", "killall", "pkill") for c in calls)


# ── device text-size (#947) ──

def test_text_size_ios_sets_category_and_restore_returns_original(monkeypatch, tmp_path, capsys, no_waiting):
    ran: list[list[str]] = []

    def fake_run(command):
        ran.append(command)
        return True, "large" if command[-1] == "content_size" else ""
    monkeypatch.setattr(text_size, "run_command", fake_run)
    real_run = subprocess.run

    def run_restore(command, **kwargs):
        if command and command[0] == "xcrun":
            ran.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        return real_run(command, **kwargs)
    monkeypatch.setattr(claims.subprocess, "run", run_restore)
    text_size.run_text_size(make_args(tmp_path, mode="largest", device=IOS_UDID))
    data = result_of(capsys)
    assert data["ok"] and data["before"] == "large" and ran[-1][-1] == "accessibility-extra-extra-extra-large"
    text_size.run_text_size(make_args(tmp_path, restore=True, device=IOS_UDID))
    assert result_of(capsys)["restored"] is True and ran[-1][-1] == "large"


def test_text_size_values():
    assert text_size._target_values("largest") == ("accessibility-extra-extra-extra-large", "2.0")
    assert text_size._target_values("1.3") == ("large", "1.3")
    assert text_size._target_values("9") is None
    assert text_size._target_values("extra-large") == ("extra-large", "1.0")
