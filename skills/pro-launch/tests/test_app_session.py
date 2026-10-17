"""iOS 상주 Maestro 세션 (#894 2단계) · Android 화면 구조 읽기 견고화.

기기 없이 돈다: 중계는 가짜 `maestro` 실행 파일(표준입출력 MCP 흉내)로, 클라이언트는 진짜 로컬 소켓으로 시험한다.
실기기 측정은 맨 아래 local_only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import app_input  # noqa: E402
import maestro_session  # noqa: E402
import maestro_session_relay  # noqa: E402
from pro_launch.commands.app.actions import run, session, tree  # noqa: E402
from pro_launch.runtime import devices as rt_devices  # noqa: E402

IOS_UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"
DEVICES = {"android": ["emulator-5554"], "ios_booted": [f"iPhone 16 [{IOS_UDID}]"],
           "android_avds": [], "adb_path": "/x/adb", "emulator_path": None}
INSPECT_TEXT = json.dumps({
    "ui_schema": {"platform": "ios", "abbreviations": {"b": "bounds", "txt": "text", "rid": "resource-id",
                                                       "a11y": "accessibilityText", "c": "children"}},
    "elements": [{"b": "[0,0][440,956]", "c": [
        {"b": "[24,407][416,457]", "a11y": "로그인"},
        {"b": "[24,469][416,519]", "rid": "signup_button", "txt": "가입"}]}]}, ensure_ascii=False)


def result_of(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


# ── 순수 함수 ────────────────────────────────────────────────────────────

def test_inspect_screen_compact_schema_becomes_the_same_nodes():
    nodes = app_input.maestro_inspect_nodes(INSPECT_TEXT)
    assert [(n["text"], n["id"]) for n in nodes] == [("로그인", ""), ("가입", "signup_button")]
    assert nodes[0]["center"] == [220, 432]
    assert app_input.maestro_inspect_nodes("not json") == []


@pytest.mark.parametrize("available,mapping,missing", [
    (["run", "inspect_screen", "list_devices"], {"run": "run", "inspect": "inspect_screen"}, []),
    (["run_flow", "inspect_screen"], {"run": "run_flow", "inspect": "inspect_screen"}, []),
    (["take_screenshot"], {}, ["run", "inspect"]),
])
def test_tool_names_are_mapped_per_maestro_version(available, mapping, missing):
    assert maestro_session.resolve_tool_names(available) == (mapping, missing)


def test_flow_outcome_reads_success_failure_and_never_echoes_env():
    ok_text = json.dumps({"success": True, "message": "Flow executed successfully", "env_vars": {"X": "secret!"}})
    is_success, lines = maestro_session.flow_outcome({"is_error": False, "text": ok_text, "reconnected": False})
    assert is_success and "secret!" not in " ".join(lines)
    is_success, lines = maestro_session.flow_outcome(
        {"is_error": True, "text": "Failed to run flow: Element not found: Text matching regex: x", "reconnected": False})
    assert not is_success and "not found" in lines[0]


# ── 클라이언트 ↔ 진짜 소켓 ──────────────────────────────────────────────

def _one_shot_server(reply: dict) -> tuple[int, list]:
    """요청 한 번을 받아 reply 를 돌려주는 로컬 서버 > (포트, 받은 요청 목록)."""
    server = socket.create_server(("127.0.0.1", 0))
    received: list = []

    def serve():
        connection, _ = server.accept()
        with connection:
            data = b""
            while not data.endswith(b"\n"):
                data += connection.recv(4096)
            received.append(json.loads(data))
            connection.sendall((json.dumps(reply) + "\n").encode())
        server.close()
    threading.Thread(target=serve, daemon=True).start()
    return server.getsockname()[1], received


def _write_ready_session(port: int, token: str = "t0ken") -> Path:
    path = maestro_session.session_file(IOS_UDID)
    maestro_session.write_session(path, {"status": "ready", "port": port, "token": token,
                                         "relay_pid": os.getpid(), "device": IOS_UDID})
    return path


def test_call_without_session_is_silent():
    assert maestro_session.call(IOS_UDID, "run", {}, 5) == (None, None)


def test_call_goes_through_socket_with_token():
    port, received = _one_shot_server({"ok": True, "is_error": False, "text": "{}", "reconnected": True})
    _write_ready_session(port)
    result, reason = maestro_session.call(IOS_UDID, "inspect", {}, 5)
    assert reason is None and result["reconnected"] is True
    assert received[0]["token"] == "t0ken" and received[0]["tool"] == "inspect"


def test_session_file_is_private():
    path = _write_ready_session(1)
    if os.name == "posix":
        assert (path.stat().st_mode & 0o777) == 0o600


def test_dead_relay_falls_back_and_cleans_its_file():
    server = socket.create_server(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.close()   # 아무도 안 듣는 포트
    path = _write_ready_session(port)
    assert maestro_session.call(IOS_UDID, "run", {}, 5) == (None, "session_gone")
    assert not path.exists()


def test_starting_session_is_not_used():
    maestro_session.write_session(maestro_session.session_file(IOS_UDID), {"status": "starting"})
    assert maestro_session.call(IOS_UDID, "run", {}, 5) == (None, "session_not_ready")


# ── 중계: 가짜 maestro (표준입출력 MCP) ─────────────────────────────────

FAKE_MAESTRO = textwrap.dedent('''\
    #!{python}
    import json, sys
    if "--no-viewer" in sys.argv and {old_version}:
        sys.stderr.write("Unknown option: '--no-viewer'\\n"); sys.exit(2)
    sys.stderr.write("mcp_viewer_ready http://127.0.0.1:10000\\n"); sys.stderr.flush()
    import os
    tools = {tools}
    # 끊김은 프로세스를 다시 띄워도 이어지지 않게 파일로 센다 (실제: 다시 붙으면 낫는다)
    marker = {marker!r}
    unreachable_left = [0 if os.path.exists(marker) else {unreachable}]
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:
            continue
        method, params = message["method"], message.get("params", {{}})
        if method == "initialize":
            result = {{"protocolVersion": "2024-11-05"}}
        elif method == "tools/list":
            result = {{"tools": [{{"name": n}} for n in tools]}}
        else:
            name, args = params["name"], params["arguments"]
            if name == "inspect_screen":
                result = {{"content": [{{"type": "text", "text": "{{\\"elements\\": []}}"}}], "isError": False}}
            elif unreachable_left[0] > 0 and args.get("yaml"):
                unreachable_left[0] -= 1
                open(marker, "w").close()
                result = {{"content": [{{"type": "text", "text": "Failed to run flow: Device became unreachable during deviceInfo"}}], "isError": True}}
            else:
                result = {{"content": [{{"type": "text", "text": json.dumps({{"success": True, "device": args["device_id"]}})}}], "isError": False}}
        print(json.dumps({{"jsonrpc": "2.0", "id": message["id"], "result": result}}), flush=True)
''')


def _fake_maestro(tmp_path, tools=("run", "inspect_screen"), is_old_version=False, unreachable=0) -> str:
    path = tmp_path / "maestro"
    path.write_text(FAKE_MAESTRO.format(python=sys.executable, tools=list(tools),
                                        old_version=is_old_version, unreachable=unreachable,
                                        marker=str(tmp_path / "unreachable.done")), encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def _serve_in_thread(tmp_path, maestro_path, idle_minutes=5.0):
    state_path = maestro_session.session_file(IOS_UDID)
    relay = maestro_session_relay.Relay(IOS_UDID, idle_minutes, maestro_path, state_path)
    thread = threading.Thread(target=relay.serve, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        state = maestro_session.read_session(IOS_UDID) or {}
        if state.get("status") in ("ready", "failed"):
            return relay, thread, state
        time.sleep(0.05)
    raise AssertionError("relay never settled")


@pytest.mark.skipif(os.name != "posix", reason="가짜 maestro 는 shebang 실행 파일이다")
def test_relay_serves_calls_reconnects_and_stops(tmp_path):
    relay, thread, state = _serve_in_thread(tmp_path, _fake_maestro(tmp_path, unreachable=1))
    assert state["status"] == "ready" and state["tools"] == {"run": "run", "inspect": "inspect_screen"}
    assert state["viewer"]["is_disabled"] is True
    # 첫 run 은 '기기 연결 끊김' — 중계가 maestro mcp 를 다시 띄워 한 번 더 부른다
    result, reason = maestro_session.call(IOS_UDID, "run", {"yaml": "appId: x\n---\n- back\n"}, 10)
    assert reason is None and result["reconnected"] is True and not result["is_error"]
    assert IOS_UDID in result["text"], "device_id 를 중계가 채워야 한다"
    assert maestro_session.request(maestro_session.read_session(IOS_UDID), {"op": "stop"}, 5)["ok"]
    thread.join(10)
    assert not thread.is_alive() and maestro_session.read_session(IOS_UDID) is None


@pytest.mark.skipif(os.name != "posix", reason="가짜 maestro 는 shebang 실행 파일이다")
def test_relay_rejects_wrong_token(tmp_path):
    _, thread, state = _serve_in_thread(tmp_path, _fake_maestro(tmp_path))
    reply = maestro_session.request({**state, "token": "wrong"}, {"op": "ping"}, 5)
    assert reply == {"ok": False, "reason": "session_token_mismatch"}
    maestro_session.request(state, {"op": "stop"}, 5)
    thread.join(10)


@pytest.mark.skipif(os.name != "posix", reason="가짜 maestro 는 shebang 실행 파일이다")
def test_relay_on_old_maestro_runs_with_viewer_and_reports_its_port(tmp_path):
    _, thread, state = _serve_in_thread(tmp_path, _fake_maestro(tmp_path, is_old_version=True))
    assert state["status"] == "ready"
    assert state["viewer"] == {"is_disabled": False, "url": "http://127.0.0.1:10000"}
    maestro_session.request(state, {"op": "stop"}, 5)
    thread.join(10)


@pytest.mark.skipif(os.name != "posix", reason="가짜 maestro 는 shebang 실행 파일이다")
def test_relay_without_needed_tools_fails_with_reason(tmp_path):
    _, thread, state = _serve_in_thread(tmp_path, _fake_maestro(tmp_path, tools=("take_screenshot",)))
    thread.join(10)
    assert state["status"] == "failed" and state["reason"] == "session_tools_missing"
    assert state["missing"] == ["run", "inspect"]


@pytest.mark.skipif(os.name != "posix", reason="가짜 maestro 는 shebang 실행 파일이다")
def test_relay_stops_itself_when_idle(tmp_path):
    _, thread, _ = _serve_in_thread(tmp_path, _fake_maestro(tmp_path), idle_minutes=0.02)
    thread.join(15)
    assert not thread.is_alive() and maestro_session.read_session(IOS_UDID) is None


# ── 백엔드 라우팅 ────────────────────────────────────────────────────────

class RecordingRun:
    """subprocess.run 대역 — maestro·xcrun 호출을 기록한다."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        stdout = "" if command[0] != "/x/maestro" else "Tap... COMPLETED"
        return subprocess.CompletedProcess(command, 0, stdout, "")


@pytest.fixture
def ios(monkeypatch):
    monkeypatch.setattr(rt_devices, "list_devices", lambda: DEVICES)
    monkeypatch.setattr(app_input.IOSMaestroBackend, "_maestro", staticmethod(lambda: "/x/maestro"))
    monkeypatch.delenv("DEV", raising=False)
    monkeypatch.delenv("PKG", raising=False)
    recorder = RecordingRun()
    monkeypatch.setattr(app_input.subprocess, "run", recorder)
    return recorder


def _session_calls(monkeypatch, replies: list):
    """maestro_session.call 대역 — 차례로 replies 를 돌려주고 받은 (도구, 인자) 를 기록한다."""
    seen: list = []
    _write_ready_session(1)

    def fake_call(device, tool, arguments, timeout_seconds):
        seen.append((tool, arguments))
        return replies.pop(0)
    monkeypatch.setattr(maestro_session, "call", fake_call)
    return seen


def test_tree_uses_session_without_spawning_maestro(ios, monkeypatch, tmp_path, capsys):
    seen = _session_calls(monkeypatch, [({"is_error": False, "text": INSPECT_TEXT, "reconnected": False}, None)])
    tree._app_tree(argparse.Namespace(root=str(tmp_path), device=IOS_UDID, pkg=None))
    data = result_of(capsys)
    assert data["ok"] and data["transport"] == "session" and data["count"] == 2
    assert seen[0][0] == "inspect" and not [c for c in ios.calls if c[0] == "/x/maestro"]


def test_unusable_session_falls_back_to_per_call_and_says_why(ios, monkeypatch, tmp_path, capsys):
    _session_calls(monkeypatch, [(None, "session_gone")])
    be = app_input.IOSMaestroBackend()
    is_success, detail = be.tap_ratio(IOS_UDID, 0.5, 0.5)
    assert is_success and [c for c in ios.calls if c[0] == "/x/maestro"]
    assert be.session_report == {"transport": "per_call", "session_fallback": "session_gone"}


def test_secret_input_never_goes_through_session_and_keeps_logs_in_temp(ios, monkeypatch):
    seen = _session_calls(monkeypatch, [])
    be = app_input.IOSMaestroBackend()
    be.input_text(IOS_UDID, "s3cret", submit=False)
    assert seen == [], "비밀 값이 세션으로 갔다"
    command = next(c for c in ios.calls if c[0] == "/x/maestro")
    assert "--debug-output" in command and "--flatten-debug-output" in command and command[-1].endswith(".yaml")
    assert be.session_report["session_fallback"] == "secret_input_per_call"


def test_run_with_session_calls_each_step_and_points_at_failure(ios, monkeypatch, tmp_path, capsys):
    ok = ({"is_error": False, "text": json.dumps({"success": True}), "reconnected": False}, None)
    failed = ({"is_error": True, "text": "Failed to run flow: Element not found: Text matching regex: 홈",
               "reconnected": False}, None)
    seen = _session_calls(monkeypatch, [ok, failed])
    steps_file = tmp_path / "steps.json"
    steps_file.write_text(json.dumps([{"swipe": {"direction": "up"}}, {"wait": {"text": "홈", "timeout": 2}},
                                      {"tap": {"text": "a"}}], ensure_ascii=False), encoding="utf-8")
    run._app_run(argparse.Namespace(root=str(tmp_path), device=IOS_UDID, pkg=None, shot=None,
                                    steps=str(steps_file), started_monotonic=time.monotonic()))
    data = result_of(capsys)
    assert data["code"] == "step_failed" and data["failed_step"] == 1 and data["transport"] == "session"
    assert [s["status"] for s in data["steps"]] == ["completed", "failed", "not_run"]
    assert len(seen) == 2 and "extendedWaitUntil" in seen[1][1]["yaml"]
    assert not [c for c in ios.calls if c[0] == "/x/maestro"]


# ── session 동작 ─────────────────────────────────────────────────────────

def _session_args(tmp_path, verb, device=IOS_UDID):
    return argparse.Namespace(root=str(tmp_path), device=device, pkg=None, session_verb=verb,
                              idle_minutes=None, started_monotonic=time.monotonic())


def test_session_needs_a_verb(ios, tmp_path, capsys):
    session._app_session(_session_args(tmp_path, None))
    assert result_of(capsys)["code"] == "session_verb_required"


def test_session_is_ios_only(ios, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(app_input, "sdk_tool", lambda name: "/x/adb")
    session._app_session(_session_args(tmp_path, "start", device="emulator-5554"))
    assert result_of(capsys)["code"] == "unsupported_on_platform"


def test_session_status_cleans_stale_file(ios, monkeypatch, tmp_path, capsys):
    path = _write_ready_session(1)
    monkeypatch.setattr(session.procs, "pid_alive", lambda pid: False)
    session._app_session(_session_args(tmp_path, "status"))
    data = result_of(capsys)
    assert data["ok"] and data["is_running"] is False and data["cleaned_stale"] is True and not path.exists()


def test_session_start_failure_kills_relay_and_reports_reason(ios, monkeypatch, tmp_path, capsys):
    killed: list = []

    def fake_spawn(command, working_folder, log_path):
        maestro_session.write_session(maestro_session.session_file(IOS_UDID),
                                      {"status": "failed", "relay_pid": 4242, "reason": "device_unreachable",
                                       "detail": "Device became unreachable"})
        return 4242
    monkeypatch.setattr(session.procs, "spawn_detached", fake_spawn)
    monkeypatch.setattr(session.procs, "pid_alive", lambda pid: True)
    monkeypatch.setattr(session.procs, "kill_process_group", lambda pid, grace=5.0: killed.append(pid) or False)
    monkeypatch.setattr(session, "_relay_state", lambda dev: (None, False))
    session._app_session(_session_args(tmp_path, "start"))
    data = result_of(capsys)
    assert data["code"] == "session_start_failed" and data["reason"] == "device_unreachable" and killed == [4242]


# ── Android: 화면 구조 읽기 ──────────────────────────────────────────────

class FakeAdb:
    """AndroidBackend._adb 대역 — (인자 앞부분 > 결과) 표대로 답한다."""

    def __init__(self, dump_results: list, probe: str = "stopped\nService window: found"):
        self.dump_results, self.probe, self.calls = dump_results, probe, []

    def __call__(self, dev, *args, timeout=15, binary=False, input_text=None):
        self.calls.append(args)
        if args[:2] == ("exec-out", "uiautomator"):
            outcome = self.dump_results.pop(0)
            if outcome == "timeout":
                raise subprocess.TimeoutExpired(args, timeout)
            return subprocess.CompletedProcess(args, 0, outcome, "")
        if args[0] == "shell" and "bootanim" in args[1]:
            return subprocess.CompletedProcess(args, 0, self.probe, "")
        return subprocess.CompletedProcess(args, 0, "", "")


XML = '<hierarchy><node text="홈" resource-id="" content-desc="" clickable="true" bounds="[0,0][10,10]"/></hierarchy>'


@pytest.fixture
def android(monkeypatch):
    monkeypatch.setattr(app_input.time, "sleep", lambda s: None)
    return app_input.AndroidBackend()


def test_android_dump_timeout_is_retried(android, monkeypatch):
    fake = FakeAdb(["timeout", XML])
    monkeypatch.setattr(android, "_adb", fake)
    assert [n["text"] for n in android.nodes("emulator-5554")] == ["홈"]


def test_android_restarting_system_is_reported_without_retry(android, monkeypatch):
    fake = FakeAdb(["Killed \n"], probe="running\nService window: found")
    monkeypatch.setattr(android, "_adb", fake)
    assert android.nodes("emulator-5554") == []
    assert android.device_failure["code"] == "android_system_not_ready"
    assert sum(1 for c in fake.calls if c[:2] == ("exec-out", "uiautomator")) == 1


def test_android_ui_automation_failure_after_two_tries(android, monkeypatch):
    fake = FakeAdb(["Killed \n", "Killed \n"])
    monkeypatch.setattr(android, "_adb", fake)
    assert android.nodes("emulator-5554") == []
    assert android.device_failure["code"] == "ui_automation_unavailable"


NULL_ROOT = "ERROR: null root node returned by UiTestAutomationBridge.\n"


def test_android_no_focused_window_wakes_screen_then_reads(android, monkeypatch):
    # 재부팅 직후 실측: 초점 창이 없어 null root 가 연달아 나오다가 깨운 뒤 읽힌다
    fake = FakeAdb([NULL_ROOT, NULL_ROOT, XML])
    monkeypatch.setattr(android, "_adb", fake)
    assert [n["text"] for n in android.nodes("emulator-5554")] == ["홈"]
    assert sum(1 for c in fake.calls if c[0] == "shell" and "WAKEUP" in c[1]) == 2


def test_android_no_focused_window_reported_after_three_tries(android, monkeypatch):
    fake = FakeAdb([NULL_ROOT, NULL_ROOT, NULL_ROOT])
    monkeypatch.setattr(android, "_adb", fake)
    assert android.nodes("emulator-5554") == []
    assert android.device_failure["code"] == "no_focused_window"
    assert sum(1 for c in fake.calls if c[:2] == ("exec-out", "uiautomator")) == 3


def test_android_tree_reports_the_cause_code(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(rt_devices, "list_devices", lambda: DEVICES)
    monkeypatch.setattr(app_input, "sdk_tool", lambda name: "/x/adb")
    monkeypatch.setattr(app_input.time, "sleep", lambda s: None)
    monkeypatch.setattr(app_input.AndroidBackend, "_adb", lambda self, dev, *a, **k: FakeAdb(
        ["timeout"], probe="running")(dev, *a, **k))
    tree._app_tree(argparse.Namespace(root=str(tmp_path), device="emulator-5554", pkg=None))
    data = result_of(capsys)
    assert data["ok"] is False and data["code"] in ("ui_dump_timeout", "android_system_not_ready")


# ── 실기기 (로컬만) ──────────────────────────────────────────────────────

def _booted_udid() -> str | None:
    if not shutil.which("xcrun"):
        return None
    listed = subprocess.run(["xcrun", "simctl", "list", "devices", "booted", "-j"], capture_output=True, text=True)
    for runtime_devices in json.loads(listed.stdout or "{}").get("devices", {}).values():
        for device in runtime_devices:
            if device.get("state") == "Booted":
                return device["udid"]
    return None


@pytest.mark.local_only
def test_real_session_tree_is_fast(tmp_path):
    """부팅된 시뮬레이터 + Maestro 가 있으면: 세션 시작 > tree 2회 (두 번째가 3초 안) > 끝."""
    udid = _booted_udid()
    if not udid or not app_input.IOSMaestroBackend().available():
        pytest.skip("부팅된 iOS 시뮬레이터·Maestro 없음")
    cli = [sys.executable, str(SCRIPTS / "launch_cli.py"), "app"]
    env = {**os.environ, "PROJECTOPS_HOME": str(tmp_path / "home")}
    started = json.loads(subprocess.run(cli + ["session", "start", "--device", udid, "--root", str(tmp_path)],
                                        capture_output=True, text=True, env=env, timeout=200).stdout)
    try:
        assert started["ok"], started
        for _ in range(2):
            began = time.monotonic()
            tree_result = json.loads(subprocess.run(cli + ["tree", "--device", udid, "--root", str(tmp_path)],
                                                    capture_output=True, text=True, env=env, timeout=120).stdout)
        assert tree_result["transport"] == "session" and time.monotonic() - began < 5
    finally:
        subprocess.run(cli + ["session", "stop", "--device", udid, "--root", str(tmp_path)],
                       capture_output=True, text=True, env=env, timeout=60)
