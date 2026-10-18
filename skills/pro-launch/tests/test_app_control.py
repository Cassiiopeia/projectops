"""app 앱 제어 동작 (#893) · iOS app type (#895) — 기기 없이 subprocess 를 가짜로 바꿔 검사한다."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import app_input  # noqa: E402
from pro_launch.commands.app import app_control  # noqa: E402
from pro_launch.commands.app.actions import (location, openurl, permission, push, relaunch,  # noqa: E402
                                             terminate, type_)
from pro_launch.runtime import devices as rt_devices  # noqa: E402
from pro_launch.runtime import foreground  # noqa: E402

IOS_UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"
DEVICES = {"android": ["emulator-5554", "R5CT1234"],
           "ios_booted": [f"iPhone 16 [{IOS_UDID}]"],
           "android_avds": [], "adb_path": "/x/adb", "emulator_path": None}


# 가짜로 바꿀 기기 도구. 그 밖(git 등 루트 해석)은 진짜 subprocess.run 으로 보낸다
DEVICE_TOOLS = ("/x/adb", "xcrun", "/x/maestro")
REAL_RUN = subprocess.run


class FakeRun:
    """subprocess.run 대역 — 기기 도구 명령만 기록하고 정해 둔 결과를 돌려준다."""

    def __init__(self, results=None):
        self.calls: list[list[str]] = []
        self.envs: list[dict | None] = []
        self.results = list(results or [])

    def __call__(self, command, **kwargs):
        if not command or command[0] not in DEVICE_TOOLS:
            return REAL_RUN(command, **kwargs)
        self.calls.append(list(command))
        self.envs.append(kwargs.get("env"))
        returncode, stdout, stderr = self.results.pop(0) if self.results else (0, "", "")
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)


@pytest.fixture
def fake_run(monkeypatch, tmp_path):
    monkeypatch.setattr(rt_devices, "list_devices", lambda: DEVICES)
    monkeypatch.setattr(app_control, "sdk_tool", lambda name: "/x/adb")
    # 띄운 뒤 앞에 있는지 확인(#923)도 같은 가짜 도구를 쓰고, iOS 대기는 건너뛴다
    monkeypatch.setattr(foreground, "sdk_tool", lambda name: "/x/adb")
    monkeypatch.setattr(foreground, "IOS_SETTLE_SECONDS", 0)
    monkeypatch.delenv("DEV", raising=False)
    monkeypatch.delenv("PKG", raising=False)
    runner = FakeRun()
    monkeypatch.setattr(app_control.subprocess, "run", runner)
    return runner


def make_args(tmp_path, **values):
    base = dict(root=str(tmp_path), device="emulator-5554", pkg="com.acme.app", lat=None, lon=None,
                service=None, grant=False, revoke=False, payload=None, url=None)
    base.update(values)
    return argparse.Namespace(**base)


def result_of(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


# ── terminate · relaunch ────────────────────────────────────────────────

def test_android_terminate_uses_force_stop(fake_run, tmp_path, capsys):
    terminate._app_terminate(make_args(tmp_path))
    data = result_of(capsys)
    assert data["ok"] and data["code"] == "ok" and data["was_running"] is None
    assert fake_run.calls[0] == ["/x/adb", "-s", "emulator-5554", "shell", "am", "force-stop", "com.acme.app"]


def test_ios_terminate_of_stopped_app_is_not_a_failure(fake_run, tmp_path, capsys):
    fake_run.results = [(3, "", "found nothing to terminate")]
    terminate._app_terminate(make_args(tmp_path, device=IOS_UDID))
    data = result_of(capsys)
    assert data["ok"] and data["was_running"] is False
    assert fake_run.calls[0] == ["xcrun", "simctl", "terminate", IOS_UDID, "com.acme.app"]


def test_terminate_without_package_asks_for_it(fake_run, tmp_path, capsys):
    terminate._app_terminate(make_args(tmp_path, pkg=None))
    assert result_of(capsys)["code"] == "package_required"
    assert fake_run.calls == []


def test_relaunch_terminates_then_launches(fake_run, tmp_path, capsys):
    fake_run.results = [(0, "", ""), (0, "Events injected: 1", "")]
    relaunch._app_relaunch(make_args(tmp_path))
    assert result_of(capsys)["ok"]
    assert "force-stop" in fake_run.calls[0] and "monkey" in fake_run.calls[1]


def test_relaunch_stops_when_terminate_fails(fake_run, tmp_path, capsys):
    fake_run.results = [(1, "", "boom")]
    relaunch._app_relaunch(make_args(tmp_path, device=IOS_UDID))
    assert result_of(capsys)["code"] == "terminate_failed"
    assert len(fake_run.calls) == 1, "끄기 실패 뒤에 띄우면 재시작이 아니다"


def test_relaunch_reports_launch_failure(fake_run, tmp_path, capsys):
    fake_run.results = [(0, "", ""), (0, "monkey aborted", "")]
    relaunch._app_relaunch(make_args(tmp_path))
    assert result_of(capsys)["code"] == "launch_failed"


# ── location ─────────────────────────────────────────────────────────────

def test_location_rejects_out_of_range(fake_run, tmp_path, capsys):
    location._app_location(make_args(tmp_path, lat=137.0, lon=10.0))
    assert result_of(capsys)["code"] == "bad_coordinates"


def test_ios_location_uses_simctl_lat_lon(fake_run, tmp_path, capsys):
    location._app_location(make_args(tmp_path, device=IOS_UDID, lat=37.5, lon=127.0))
    assert result_of(capsys)["ok"]
    assert fake_run.calls[0] == ["xcrun", "simctl", "location", IOS_UDID, "set", "37.5,127.0"]


def test_android_emulator_location_passes_longitude_first(fake_run, tmp_path, capsys):
    fake_run.results = [(0, "OK", "")]
    location._app_location(make_args(tmp_path, lat=37.5, lon=127.0))
    assert result_of(capsys)["ok"]
    assert fake_run.calls[0][-5:] == ["emu", "geo", "fix", "127.0", "37.5"]


def test_android_real_device_location_is_unsupported(fake_run, tmp_path, capsys):
    location._app_location(make_args(tmp_path, device="R5CT1234", lat=37.5, lon=127.0))
    data = result_of(capsys)
    assert data["code"] == "unsupported_on_platform" and data["next"]
    assert fake_run.calls == []


# ── permission ──────────────────────────────────────────────────────────

def test_permission_needs_exactly_one_mode(fake_run, tmp_path, capsys):
    permission._app_permission(make_args(tmp_path, service="camera", grant=True, revoke=True))
    assert result_of(capsys)["code"] == "permission_mode_required"


def test_ios_permission_uses_simctl_privacy(fake_run, tmp_path, capsys):
    permission._app_permission(make_args(tmp_path, device=IOS_UDID, service="photos", grant=True))
    assert result_of(capsys)["ok"]
    assert fake_run.calls[0] == ["xcrun", "simctl", "privacy", IOS_UDID, "grant", "photos", "com.acme.app"]


def test_android_location_permission_grants_both_precisions(fake_run, tmp_path, capsys):
    permission._app_permission(make_args(tmp_path, service="location", revoke=True))
    assert result_of(capsys)["ok"]
    assert [c[-1] for c in fake_run.calls] == ["android.permission.ACCESS_FINE_LOCATION",
                                              "android.permission.ACCESS_COARSE_LOCATION"]
    assert all(c[4:6] == ["pm", "revoke"] for c in fake_run.calls)


def test_android_permission_failure_in_output_is_detected(fake_run, tmp_path, capsys):
    # pm grant 은 기기 쪽 예외를 종료코드 0 으로 돌려주는 일이 있다
    fake_run.results = [(0, "Exception occurred while executing 'grant'", "")]
    permission._app_permission(make_args(tmp_path, service="android.permission.CAMERA", grant=True))
    assert result_of(capsys)["code"] == "permission_failed"


def test_permission_service_of_other_platform_is_unsupported(fake_run, tmp_path, capsys):
    permission._app_permission(make_args(tmp_path, device=IOS_UDID, service="camera", grant=True))
    assert result_of(capsys)["code"] == "unsupported_on_platform"
    permission._app_permission(make_args(tmp_path, service="nonsense", grant=True))
    data = result_of(capsys)
    assert data["code"] == "unknown_permission_service" and "camera" in data["candidates"]


# ── push ─────────────────────────────────────────────────────────────────

def _payload(tmp_path, content) -> str:
    path = tmp_path / "push.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return str(path)


def test_push_rejects_bad_payload(fake_run, tmp_path, capsys):
    push._app_push(make_args(tmp_path, device=IOS_UDID, payload=_payload(tmp_path, "{not json")))
    assert result_of(capsys)["code"] == "payload_invalid"
    push._app_push(make_args(tmp_path, device=IOS_UDID, payload=str(tmp_path / "missing.json")))
    assert result_of(capsys)["code"] == "payload_invalid"


def test_ios_push_sends_through_simctl(fake_run, tmp_path, capsys):
    path = _payload(tmp_path, {"aps": {"alert": "hi"}})
    push._app_push(make_args(tmp_path, device=IOS_UDID, payload=path))
    assert result_of(capsys)["ok"]
    assert fake_run.calls[0] == ["xcrun", "simctl", "push", IOS_UDID, "com.acme.app", path]


def test_ios_push_with_bundle_in_payload_needs_no_package(fake_run, tmp_path, capsys):
    path = _payload(tmp_path, {"aps": {"alert": "hi"}, "Simulator Target Bundle": "com.acme.app"})
    push._app_push(make_args(tmp_path, device=IOS_UDID, pkg=None, payload=path))
    assert result_of(capsys)["ok"]
    assert fake_run.calls[0] == ["xcrun", "simctl", "push", IOS_UDID, path]


def test_android_push_is_unsupported(fake_run, tmp_path, capsys):
    push._app_push(make_args(tmp_path, payload=_payload(tmp_path, {"aps": {}})))
    data = result_of(capsys)
    assert data["code"] == "unsupported_on_platform" and data["action"] == "push" and data["next"]
    assert fake_run.calls == []


# ── openurl ──────────────────────────────────────────────────────────────

def test_openurl_requires_scheme(fake_run, tmp_path, capsys):
    openurl._app_openurl(make_args(tmp_path, url="just-a-path"))
    assert result_of(capsys)["code"] == "url_required"


def test_android_openurl_quotes_url_for_device_shell(fake_run, tmp_path, capsys):
    openurl._app_openurl(make_args(tmp_path, pkg=None, url="myapp://x?a=1&b=2"))
    assert result_of(capsys)["ok"]
    command = fake_run.calls[0]
    assert command[command.index("-d") + 1] == "'myapp://x?a=1&b=2'"
    assert "-p" not in command


def test_android_openurl_reports_unresolved_intent(fake_run, tmp_path, capsys):
    fake_run.results = [(0, "Error: Activity not started, unable to resolve Intent", "")]
    openurl._app_openurl(make_args(tmp_path, url="nosuch://x"))
    assert result_of(capsys)["code"] == "openurl_failed"


def test_ios_openurl_uses_simctl(fake_run, tmp_path, capsys):
    openurl._app_openurl(make_args(tmp_path, device=IOS_UDID, url="myapp://home"))
    assert result_of(capsys)["ok"]
    assert fake_run.calls[0] == ["xcrun", "simctl", "openurl", IOS_UDID, "myapp://home"]


def test_tool_timeout_becomes_failure_not_exception(monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired("x", 30)
    monkeypatch.setattr(app_control.subprocess, "run", boom)
    ok, detail = app_control.run_tool(["xcrun"])
    assert ok is False and "30" in detail


# ── iOS app type (#895) ─────────────────────────────────────────────────

SECRET = "Pa ss&w0rd!"


@pytest.fixture
def ios_type(monkeypatch):
    monkeypatch.setattr(rt_devices, "list_devices", lambda: DEVICES)
    monkeypatch.setenv("PL_TEST_SECRET", SECRET)
    runner = FakeRun()
    monkeypatch.setattr(app_input.subprocess, "run", runner)
    return runner


def _type_args(**values):
    base = dict(device=IOS_UDID, pkg=None, cred=None, cred_field=None, text_env="PL_TEST_SECRET", submit=False)
    base.update(values)
    return argparse.Namespace(**base)


def test_ios_type_goes_through_maestro_env_not_argv(ios_type, monkeypatch, capsys):
    monkeypatch.setattr(app_input.IOSMaestroBackend, "_maestro", staticmethod(lambda: "/x/maestro"))
    flows = []
    real_flow = app_input.maestro_flow
    monkeypatch.setattr(app_input, "maestro_flow", lambda c, a: flows.append(real_flow(c, a)) or flows[-1])
    type_._app_type(_type_args(submit=True))
    data = result_of(capsys)
    assert data["ok"] and data["via"] == "ios" and data["submitted"] and data["chars"] == len(SECRET)
    assert SECRET not in " ".join(ios_type.calls[0]), "값이 명령줄에 실렸다"
    assert SECRET not in flows[0], "값이 flow 파일에 실렸다"
    assert "${" + app_input.INPUT_TEXT_ENV + "}" in flows[0] and "pressKey" in flows[0]
    assert ios_type.envs[0][app_input.INPUT_TEXT_ENV] == SECRET
    assert SECRET not in json.dumps(data)


def test_ios_type_failure_masks_secret(ios_type, monkeypatch, capsys):
    monkeypatch.setattr(app_input.IOSMaestroBackend, "_maestro", staticmethod(lambda: "/x/maestro"))
    ios_type.results = [(1, f"Input text {SECRET} FAILED", "")]
    type_._app_type(_type_args())
    data = result_of(capsys)
    assert data["code"] == "app_type_failed" and SECRET not in json.dumps(data)


def test_ios_type_without_maestro_reports_tool_missing(ios_type, monkeypatch, capsys):
    monkeypatch.setattr(app_input.IOSMaestroBackend, "_maestro", staticmethod(lambda: None))
    type_._app_type(_type_args())
    data = result_of(capsys)
    assert data["code"] == "ios_tool_missing" and "maestro" in data["next"]
    assert ios_type.calls == []


@pytest.mark.local_only
def test_ios_location_on_booted_simulator():
    """부팅된 iOS 시뮬레이터가 있으면 실제로 위치를 바꾼다."""
    listing = subprocess.run(["xcrun", "simctl", "list", "devices", "booted"],
                             capture_output=True, text=True).stdout if os.path.exists("/usr/bin/xcrun") else ""
    import re
    found = re.search(r"\(([\w-]{36})\) \(Booted\)", listing)
    if not found:
        pytest.skip("부팅된 iOS 시뮬레이터 없음")
    r = subprocess.run([sys.executable, str(SCRIPTS / "launch_cli.py"), "app", "location",
                        "--device", found.group(1), "--lat", "37.5665", "--lon", "126.978"],
                       capture_output=True, text=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert json.loads(r.stdout.strip().splitlines()[-1])["ok"] is True
