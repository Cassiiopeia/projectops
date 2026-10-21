"""app flow — 프로젝트 Maestro flow 실행 통로 (#862). 기기 없이 subprocess 를 가짜로 바꿔 검사한다."""
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

import app_input  # noqa: E402
from pro_launch.commands.app.actions import flow  # noqa: E402
from pro_launch.runtime import devices as rt_devices  # noqa: E402

IOS_UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"
DEVICES = {"android": ["emulator-5554"], "ios_booted": [f"iPhone 16 [{IOS_UDID}]"],
           "android_avds": [], "adb_path": "/x/adb", "emulator_path": None}
REAL_RUN = subprocess.run
# Maestro 2.10 평문 출력 모양 (iOS 시뮬레이터 실측)
PASSED_OUTPUT = ("Running on iPhone SE\n > Flow f\nSwipe from (50%,70%) to (50%,40%) in 400 ms... COMPLETED\n"
                 "Take screenshot after_swipe... COMPLETED\nTap on \"되돌리기\"... COMPLETED\n")
DRIVER_TIMEOUT_OUTPUT = "Maestro Android driver did not start up in time --- emulator [ emulator-5554 ]\n"


class FakeRun:
    """기기 도구 명령을 기록하고, maestro test 면 정해 둔 결과와 takeScreenshot 파일을 만든다."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.results: list[tuple[int, str]] = []
        self.screenshot_names: list[str] = []

    def __call__(self, command, **kwargs):
        if not command or command[0] not in ("/x/adb", "/x/maestro"):
            return REAL_RUN(command, **kwargs)
        self.calls.append(list(command))
        if command[0] == "/x/maestro":
            output_folder = Path(command[command.index("--test-output-dir") + 1])
            shot_folder = output_folder / "2026-10-17_233137" / "f" / "takeScreenshot"
            shot_folder.mkdir(parents=True, exist_ok=True)
            for name in self.screenshot_names:
                (shot_folder / f"{name}.png").write_bytes(b"\x89PNG fake")
            returncode, stdout = self.results.pop(0) if self.results else (0, PASSED_OUTPUT)
            return subprocess.CompletedProcess(command, returncode, stdout, "")
        return subprocess.CompletedProcess(command, 0, "", "")


@pytest.fixture
def fake_run(monkeypatch, tmp_path):
    monkeypatch.setattr(rt_devices, "list_devices", lambda: DEVICES)
    monkeypatch.setattr(app_input, "sdk_tool", lambda name: "/x/adb")
    monkeypatch.setattr(app_input.IOSMaestroBackend, "_maestro", staticmethod(lambda: "/x/maestro"))
    monkeypatch.setenv("SHOT_DIR", str(tmp_path / "shots"))
    runner = FakeRun()
    monkeypatch.setattr(subprocess, "run", runner)
    return runner


def make_args(tmp_path, device=IOS_UDID, file_text="appId: a\n---\n- back\n", **values):
    flow_file = tmp_path / "f.yaml"
    flow_file.write_text(file_text, encoding="utf-8")
    base = dict(root=str(tmp_path), device=device, pkg=None, shot=None, file=str(flow_file), timeout=None,
                keep_format=True, quality=80, max_side=0, started_monotonic=time.monotonic())
    base.update(values)
    return argparse.Namespace(**base)


def result_of(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_android_driver_timeout_force_stops_driver_and_retries_once(fake_run, tmp_path, capsys):
    fake_run.results = [(1, DRIVER_TIMEOUT_OUTPUT), (1, DRIVER_TIMEOUT_OUTPUT)]
    flow._app_flow(make_args(tmp_path, device="emulator-5554"))
    result = result_of(capsys)
    assert result["code"] == "maestro_driver_timeout" and result["driver_retried"] is True
    assert "overloaded" in result["next"]
    force_stopped = [c[-1] for c in fake_run.calls if c[0] == "/x/adb" and "force-stop" in c]
    assert force_stopped == list(flow.ANDROID_MAESTRO_DRIVER_PACKAGES)
    assert sum(1 for c in fake_run.calls if c[0] == "/x/maestro") == 2
