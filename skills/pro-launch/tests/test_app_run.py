"""app run — 단계 여러 개를 한 번에 (#894). 기기 없이 subprocess 를 가짜로 바꿔 검사한다."""
from __future__ import annotations

import argparse
import json
import os
import re
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
from pro_launch.commands.app.actions import run, tree  # noqa: E402
from pro_launch.runtime import devices as rt_devices  # noqa: E402

IOS_UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"
DEVICES = {"android": ["emulator-5554"], "ios_booted": [f"iPhone 16 [{IOS_UDID}]"],
           "android_avds": [], "adb_path": "/x/adb", "emulator_path": None}
SECRET = "Pa ss&w0rd!"
DEVICE_TOOLS = ("/x/adb", "xcrun", "/x/maestro")
REAL_RUN = subprocess.run
ANDROID_XML = ('<hierarchy><node text="로그인" resource-id="com.acme:id/login" content-desc="" '
               'clickable="true" bounds="[0,0][100,50]"/></hierarchy>')


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


# ── 단계 파일 검증 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("steps,bad_index", [
    ([{"tap": {"text": "a"}}, {"fly": {}}], 1),                                 # 모르는 단계
    ([{"tap": {"text": "a", "color": "red"}}], 0),                              # 모르는 키
    ([{"tap": {"text": "a", "point": "0.5,0.5"}}], 0),                          # 대상 둘
    ([{"tap": {}}], 0),                                                         # 대상 없음
    ([{"tap": {"point": "540,1200"}}], 0),                                      # 픽셀 좌표
    ([{"swipe": {"direction": "sideways"}}], 0),
    ([{"swipe": {"direction": "up", "from": "0.1,0.1"}}], 0),
    ([{"type": {"text": "plain"}}], 0),                                         # 값을 파일에 직접
    ([{"type": {"env": "A", "cred": "b"}}], 0),
    ([{"wait": {"text": "홈", "timeout": 600}}], 0),
    ([{"swipe": {"direction": "up"}}, {"back": "yes"}], 1),
    ([{"tap": {"text": "a"}, "swipe": {"direction": "up"}}], 0),                # 한 원소에 키 둘
])
def test_bad_step_is_rejected_with_its_index(steps, bad_index, tmp_path):
    with pytest.raises(steps_module.StepsError) as caught:
        steps_module.load_steps(write_steps(tmp_path, steps))
    assert caught.value.step_index == bad_index


@pytest.mark.parametrize("content", ["{not json", "[]", '{"tap": {}}',
                                     json.dumps([{"back": True}] * (steps_module.MAXIMUM_STEP_COUNT + 1))])
def test_bad_file_is_rejected_without_index(content, tmp_path):
    with pytest.raises(steps_module.StepsError) as caught:
        steps_module.load_steps(write_steps(tmp_path, content))
    assert caught.value.step_index is None


def test_valid_steps_are_normalized(tmp_path):
    steps = steps_module.load_steps(write_steps(tmp_path, [
        {"tap": {"text": "로그인"}}, {"tap": {"point": [0.5, 0.8]}}, {"swipe": {"direction": "up"}},
        {"type": {"env": "PW", "submit": True}}, {"wait": {"id": "home"}}, {"back": True}]))
    assert [s["kind"] for s in steps] == ["tap", "tap", "swipe", "type", "wait", "back"]
    assert steps[1]["point"] == (0.5, 0.8) and steps[4]["timeout"] == steps_module.DEFAULT_WAIT_SECONDS


def test_bad_steps_file_becomes_bad_steps_code(fake_run, tmp_path, capsys):
    run._app_run(make_args(tmp_path, [{"tap": {"text": "a"}}, {"fly": {}}]))
    data = result_of(capsys)
    assert data["code"] == "bad_steps" and data["step_index"] == 1 and fake_run.calls == []


def test_step_statuses_split_by_command_count():
    statuses = [("Input text ***", "COMPLETED"), ("Press Enter key", "COMPLETED"), ("Tap on x", "FAILED")]
    assert steps_module.step_statuses([2, 1, 1], statuses) == ["completed", "failed", "not_run"]


# ── iOS: Maestro 한 번 ───────────────────────────────────────────────────

IOS_STEPS = [{"tap": {"text": "로그인 (beta)"}}, {"type": {"env": "PL_TEST_SECRET", "submit": True}},
             {"wait": {"text": "홈", "timeout": 5}}, {"swipe": {"direction": "up"}}]


def test_ios_runs_every_step_in_one_maestro_call(fake_run, tmp_path, capsys):
    fake_run.results = [(0, "Tap on ...COMPLETED", "")]
    run._app_run(make_args(tmp_path, IOS_STEPS))
    data = result_of(capsys)
    assert data["ok"] and data["code"] == "ok" and data["steps_completed"] == 4
    assert [c for c in fake_run.calls if c[0] == "/x/maestro"] == [fake_run.calls[0]], "Maestro 를 여러 번 띄웠다"
    flow = fake_run.flows[0]
    for command in ("tapOn", "inputText", "pressKey", "extendedWaitUntil", "swipe"):
        assert command in flow
    assert json.dumps(re.escape("로그인 (beta)"), ensure_ascii=False) in flow and "timeout: 5000" in flow
    assert isinstance(data["elapsed_seconds"], float)


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


def test_ios_crash_before_any_step_marks_steps_unknown(fake_run, tmp_path, capsys):
    fake_run.results = [(1, "Maestro driver did not start up in time", "")]
    run._app_run(make_args(tmp_path, IOS_STEPS))
    data = result_of(capsys)
    assert data["code"] == "step_failed" and data["failed_step"] is None
    assert {s["status"] for s in data["steps"]} == {"unknown"}


def test_ios_back_step_is_rejected_before_running(fake_run, tmp_path, capsys):
    run._app_run(make_args(tmp_path, [{"swipe": {"direction": "up"}}, {"back": True}]))
    data = result_of(capsys)
    assert data["code"] == "step_unsupported_on_platform" and data["step_index"] == 1
    assert fake_run.calls == []


def test_missing_env_is_reported_with_step_index(fake_run, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("PL_TEST_SECRET")
    run._app_run(make_args(tmp_path, IOS_STEPS))
    data = result_of(capsys)
    assert data["code"] == "env_not_set" and data["step_index"] == 1 and fake_run.calls == []


def test_ios_without_maestro_reports_tool_missing(fake_run, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(app_input.IOSMaestroBackend, "_maestro", staticmethod(lambda: None))
    run._app_run(make_args(tmp_path, IOS_STEPS))
    assert result_of(capsys)["code"] == "ios_tool_missing"


# ── Android: 같은 단계 파일을 차례로 ─────────────────────────────────────

ANDROID_STEPS = [{"tap": {"text": "로그인"}}, {"type": {"env": "PL_TEST_SECRET", "submit": True}},
                 {"swipe": {"direction": "up"}}, {"back": True}]


def test_android_runs_steps_in_order_with_existing_backend(fake_run, tmp_path, capsys):
    # tap · 입력 · 입력창 다시 읽기(빈 출력 = 대조 생략) · Enter · 화면 크기 · swipe · back
    fake_run.results = [(0, ANDROID_XML, ""), (0, "", ""), (0, "", ""), (0, "", ""), (0, "", ""),
                        (0, "Physical size: 1080x2400", ""), (0, "", ""), (0, "", "")]
    run._app_run(make_args(tmp_path, ANDROID_STEPS, device="emulator-5554", ime="keep"))
    data = result_of(capsys)
    assert data["ok"] and data["via"] == "android" and data["steps_completed"] == 4
    shell = [c[3:] for c in fake_run.calls]
    assert shell[1] == ["shell", "input", "tap", "50", "25"]
    assert SECRET not in " ".join(" ".join(c) for c in fake_run.calls), "값이 명령줄에 실렸다"
    assert fake_run.inputs[2] == SECRET.replace(" ", "%s") + "\n"
    assert shell[4] == ["shell", "input", "keyevent", "66"] and shell[-1] == ["shell", "input", "keyevent", "4"]
    assert all("elapsed_seconds" in s for s in data["steps"])


def test_android_stops_at_first_failure(fake_run, tmp_path, capsys):
    fake_run.results = [(0, "<hierarchy/>", "")]
    run._app_run(make_args(tmp_path, ANDROID_STEPS, device="emulator-5554"))
    data = result_of(capsys)
    assert data["code"] == "step_failed" and data["failed_step"] == 0
    assert [s["status"] for s in data["steps"]] == ["failed", "not_run", "not_run", "not_run"]
    # 실패 뒤에는 기기 상태 확인(부팅 애니메이션·window 서비스) 한 번만 — 다음 단계는 부르지 않는다
    assert len(fake_run.calls) == 2 and "init.svc.bootanim" in fake_run.calls[1][-1]
    assert "cause" not in data


def test_android_wait_polls_until_visible(fake_run, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(run, "ANDROID_WAIT_POLL_SECONDS", 0)
    fake_run.results = [(0, "<hierarchy/>", ""), (0, ANDROID_XML, "")]
    run._app_run(make_args(tmp_path, [{"wait": {"text": "로그인", "timeout": 5}}], device="emulator-5554"))
    assert result_of(capsys)["ok"] and len(fake_run.calls) == 2


def test_android_rejects_non_ascii_type(fake_run, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PL_TEST_SECRET", "비밀")
    run._app_run(make_args(tmp_path, ANDROID_STEPS, device="emulator-5554"))
    data = result_of(capsys)
    assert data["code"] == "non_ascii_unsupported" and data["step_index"] == 1 and fake_run.calls == []


# ── 비용이 보이게: elapsed_seconds ───────────────────────────────────────

def test_tree_reports_elapsed_seconds(fake_run, tmp_path, capsys):
    fake_run.results = [(0, ANDROID_XML, ""), (0, "ko-KR", "")]
    tree._app_tree(make_args(tmp_path, [{"back": True}], device="emulator-5554"))
    assert isinstance(result_of(capsys)["elapsed_seconds"], float)


# ── 실제 시뮬레이터 ──────────────────────────────────────────────────────

@pytest.mark.local_only
def test_ios_run_on_booted_simulator(tmp_path):
    """부팅된 iOS 시뮬레이터 + Maestro 가 있으면 실제로 돌린다. 밀었다 되돌리기만 해 상태를 남기지 않는다."""
    listing = subprocess.run(["xcrun", "simctl", "list", "devices", "booted"],
                             capture_output=True, text=True).stdout if os.path.exists("/usr/bin/xcrun") else ""
    found = re.search(r"\(([\w-]{36})\) \(Booted\)", listing)
    if not found or not app_input.IOSMaestroBackend._maestro():
        pytest.skip("부팅된 iOS 시뮬레이터 또는 Maestro 없음")
    path = write_steps(tmp_path, [{"swipe": {"direction": "up"}}, {"swipe": {"direction": "down"}}])
    r = subprocess.run([sys.executable, str(SCRIPTS / "launch_cli.py"), "app", "run",
                        "--device", found.group(1), "--steps", path],
                       capture_output=True, text=True, timeout=300,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    data = json.loads(r.stdout.strip().splitlines()[-1])
    assert data["ok"] is True, data
    assert data["steps_completed"] == 2 and data["elapsed_seconds"] > 0
