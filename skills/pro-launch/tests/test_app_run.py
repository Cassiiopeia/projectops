"""app run — 단계 여러 개를 한 번에 (#894). 기기 없이 subprocess 를 가짜로 바꿔 검사한다."""
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
from pro_launch.commands.app import steps as steps_module  # noqa: E402
from pro_launch.commands.app.actions import run  # noqa: E402
from pro_launch.runtime import devices as rt_devices  # noqa: E402

IOS_UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"
DEVICES = {"android": ["emulator-5554"], "ios_booted": [f"iPhone 16 [{IOS_UDID}]"],
           "android_avds": [], "adb_path": "/x/adb", "emulator_path": None}
SECRET = "Pa ss&w0rd!"
DEVICE_TOOLS = ("/x/adb", "xcrun", "/x/maestro")
REAL_RUN = subprocess.run


class FakeRun:
    """subprocess.run 대역 — 기기 도구 명령·환경·표준입력·flow 내용을 기록하고 정해 둔 결과를 돌려준다."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.envs: list[dict | None] = []
        self.inputs: list[str | None] = []
        self.flows: list[str] = []
        self.results: list[tuple[int, str, str]] = []

    def __call__(self, command, **kwargs):
        if not command or command[0] not in DEVICE_TOOLS:
            return REAL_RUN(command, **kwargs)
        self.calls.append(list(command))
        self.envs.append(kwargs.get("env"))
        self.inputs.append(kwargs.get("input"))
        if command[0] == "/x/maestro" and command[-1].endswith(".yaml"):
            self.flows.append(Path(command[-1]).read_text(encoding="utf-8"))
        returncode, stdout, stderr = self.results.pop(0) if self.results else (0, "", "")
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)


@pytest.fixture
def fake_run(monkeypatch):
    monkeypatch.setattr(rt_devices, "list_devices", lambda: DEVICES)
    monkeypatch.setattr(app_input, "sdk_tool", lambda name: "/x/adb")
    monkeypatch.setattr(app_input.IOSMaestroBackend, "_maestro", staticmethod(lambda: "/x/maestro"))
    monkeypatch.delenv("DEV", raising=False)
    monkeypatch.delenv("PKG", raising=False)
    monkeypatch.setenv("PL_TEST_SECRET", SECRET)
    runner = FakeRun()
    monkeypatch.setattr(app_input.subprocess, "run", runner)
    return runner


def write_steps(tmp_path, steps) -> str:
    path = tmp_path / "steps.json"
    path.write_text(steps if isinstance(steps, str) else json.dumps(steps, ensure_ascii=False), encoding="utf-8")
    return str(path)


def make_args(tmp_path, steps, device=IOS_UDID, **values):
    base = dict(root=str(tmp_path), device=device, pkg=None, shot=None,
                steps=write_steps(tmp_path, steps), started_monotonic=time.monotonic())
    base.update(values)
    return argparse.Namespace(**base)


def result_of(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


# ── iOS: Maestro 한 번 ───────────────────────────────────────────────────

IOS_STEPS = [{"tap": {"text": "로그인 (beta)"}}, {"type": {"env": "PL_TEST_SECRET", "submit": True}},
             {"wait": {"text": "홈", "timeout": 5}}, {"swipe": {"direction": "up"}}]


def test_ios_secret_goes_only_through_maestro_env(fake_run, tmp_path, capsys):
    fake_run.results = [(1, f"Input text {SECRET}... FAILED\nAssertion is false", "")]
    run._app_run(make_args(tmp_path, IOS_STEPS))
    data = result_of(capsys)
    env_name = steps_module.STEP_TEXT_ENV_FORMAT.format(index=1)
    assert SECRET not in fake_run.flows[0], "값이 flow 파일에 실렸다"
    assert SECRET not in " ".join(fake_run.calls[0]), "값이 명령줄에 실렸다"
    assert "${" + env_name + "}" in fake_run.flows[0]
    assert fake_run.envs[0][env_name] == SECRET and env_name.startswith("MAESTRO_")
    assert SECRET not in json.dumps(data, ensure_ascii=False), "값이 결과에 실렸다"


def test_ios_failure_points_at_the_failing_step(fake_run, tmp_path, capsys):
    output = "\n".join(["Running on iPhone 16", " > Flow step",
                        'Tap on "로그인 \\(beta\\)"... COMPLETED', "Input text ***... COMPLETED",
                        "Press Enter key... COMPLETED", 'Assert that "홈" is visible... FAILED',
                        'Assertion is false: "홈" is visible'])
    fake_run.results = [(1, output, "")]
    run._app_run(make_args(tmp_path, IOS_STEPS))
    data = result_of(capsys)
    assert data["code"] == "step_failed" and data["failed_step"] == 2 and data["steps_completed"] == 2
    assert [s["status"] for s in data["steps"]] == ["completed", "completed", "failed", "not_run"]
    assert "Assertion is false" in data["error"] and "2번" in data["next"]
