"""iOS 상주 Maestro 세션 (#894 2단계) · Android 화면 구조 읽기 견고화.

기기 없이 돈다: 중계는 가짜 `maestro` 실행 파일(표준입출력 MCP 흉내)로, 클라이언트는 진짜 로컬 소켓으로 시험한다.
"""
from __future__ import annotations

import os
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
from pro_launch.runtime import devices as rt_devices  # noqa: E402

IOS_UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"
DEVICES = {"android": ["emulator-5554"], "ios_booted": [f"iPhone 16 [{IOS_UDID}]"],
           "android_avds": [], "adb_path": "/x/adb", "emulator_path": None}


# ── 클라이언트 ↔ 진짜 소켓 ──────────────────────────────────────────────


def _write_ready_session(port: int, token: str = "t0ken") -> Path:
    path = maestro_session.session_file(IOS_UDID)
    maestro_session.write_session(path, {"status": "ready", "port": port, "token": token,
                                         "relay_pid": os.getpid(), "device": IOS_UDID})
    return path


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


def test_secret_input_never_goes_through_session_and_keeps_logs_in_temp(ios, monkeypatch):
    seen = _session_calls(monkeypatch, [])
    be = app_input.IOSMaestroBackend()
    be.input_text(IOS_UDID, "s3cret", submit=False)
    assert seen == [], "비밀 값이 세션으로 갔다"
    command = next(c for c in ios.calls if c[0] == "/x/maestro")
    assert "--debug-output" in command and "--flatten-debug-output" in command and command[-1].endswith(".yaml")
    assert be.session_report["session_fallback"] == "secret_input_per_call"


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


NULL_ROOT = "ERROR: null root node returned by UiTestAutomationBridge.\n"


def test_android_no_focused_window_wakes_screen_then_reads(android, monkeypatch):
    # 재부팅 직후 실측: 초점 창이 없어 null root 가 연달아 나오다가 깨운 뒤 읽힌다
    fake = FakeAdb([NULL_ROOT, NULL_ROOT, XML])
    monkeypatch.setattr(android, "_adb", fake)
    assert [n["text"] for n in android.nodes("emulator-5554")] == ["홈"]
    assert sum(1 for c in fake.calls if c[0] == "shell" and "WAKEUP" in c[1]) == 2
