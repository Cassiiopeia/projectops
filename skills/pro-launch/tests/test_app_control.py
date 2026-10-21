"""app 앱 제어 동작 (#893) · iOS app type (#895) — 기기 없이 subprocess 를 가짜로 바꿔 검사한다."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import app_input  # noqa: E402
from pro_launch.commands.app import app_control  # noqa: E402
from pro_launch.commands.app.actions import openurl, permission, relaunch, type_  # noqa: E402
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


def test_relaunch_stops_when_terminate_fails(fake_run, tmp_path, capsys):
    fake_run.results = [(1, "", "boom")]
    relaunch._app_relaunch(make_args(tmp_path, device=IOS_UDID))
    assert result_of(capsys)["code"] == "terminate_failed"
    assert len(fake_run.calls) == 1, "끄기 실패 뒤에 띄우면 재시작이 아니다"


# ── permission ──────────────────────────────────────────────────────────


def test_android_permission_failure_in_output_is_detected(fake_run, tmp_path, capsys):
    # pm grant 은 기기 쪽 예외를 종료코드 0 으로 돌려주는 일이 있다
    fake_run.results = [(0, "Exception occurred while executing 'grant'", "")]
    permission._app_permission(make_args(tmp_path, service="android.permission.CAMERA", grant=True))
    assert result_of(capsys)["code"] == "permission_failed"


# ── openurl ──────────────────────────────────────────────────────────────


def test_android_openurl_quotes_url_for_device_shell(fake_run, tmp_path, capsys):
    openurl._app_openurl(make_args(tmp_path, pkg=None, url="myapp://x?a=1&b=2"))
    assert result_of(capsys)["ok"]
    command = fake_run.calls[0]
    assert command[command.index("-d") + 1] == "'myapp://x?a=1&b=2'"
    assert "-p" not in command


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
