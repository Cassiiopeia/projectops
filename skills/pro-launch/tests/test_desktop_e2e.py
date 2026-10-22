"""desktop 명령 E2E (#985) — 실제 창을 띄우고 launch_cli.py 를 처음부터 끝까지 부른다.

창을 앞으로 가져오고 키보드를 쓰므로 평소 테스트에서는 돌지 않는다. 둘 다 있어야 돈다:
    Windows + `desktop setup` 을 마친 venv
    PRO_LAUNCH_DESKTOP_E2E=1  (예: PRO_LAUNCH_DESKTOP_E2E=1 python -m pytest skills/pro-launch/tests/test_desktop_e2e.py -q)
상태(입력 세션·ref)는 conftest 가 돌린 임시 PROJECTOPS_HOME 에 쓰여 실제 기록을 건드리지 않는다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import desktop_input

pytestmark = [
    pytest.mark.local_only,
    pytest.mark.skipif(desktop_input.platform_key() != "windows", reason="Windows desktop backend only"),
    pytest.mark.skipif(os.environ.get("PRO_LAUNCH_DESKTOP_E2E") != "1",
                       reason="takes the keyboard and focus — opt in with PRO_LAUNCH_DESKTOP_E2E=1"),
]

LAUNCH_CLI = Path(__file__).resolve().parents[1] / "scripts" / "launch_cli.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "desktop_fixture.ps1"
TITLE = "PopsDesktopFixture"
SECRET = "hunter2-e2e"


def run(*args: str, env: dict | None = None) -> dict:
    """launch_cli.py desktop … 한 번 → 결과 JSON."""
    r = subprocess.run([sys.executable, str(LAUNCH_CLI), "desktop", *args], capture_output=True, text=True,
                       encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})}, timeout=90)
    lines = [ln for ln in r.stdout.strip().splitlines() if ln.startswith("{")]
    assert lines, f"no JSON from desktop {args}: {r.stdout[-500:]} {r.stderr[-500:]}"
    return json.loads(lines[-1])


def ref_of(text: str, **filters: str) -> int:
    found = run("find", "--window", TITLE, "--text", text, *[x for k, v in filters.items() for x in (f"--{k}", v)])
    assert found["ok"], found
    return found["items"][0]["ref"]


def status_text() -> str:
    found = run("find", "--window", TITLE, "--id", "statusLabel")
    assert found["ok"], found
    return found["items"][0]["text"]


@pytest.fixture
def fixture_window(monkeypatch):
    if run("doctor")["code"] == "desktop_deps_missing":
        pytest.skip("run `launch_cli.py desktop setup` first")
    monkeypatch.setenv("LAUNCH_SESSION", "desktop-e2e")
    proc = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(FIXTURE)])
    try:
        waited = run("wait", "--window", TITLE, "--text", "step 0", "--timeout", "30")
        assert waited["ok"], waited
        yield proc
    finally:
        run("session", "stop")
        if proc.poll() is None:
            proc.kill()


def test_installer_like_flow_end_to_end(fixture_window):
    # 깨지면: 입력 세션 없이도 화면이 바뀐다 — 사용자가 모르는 사이 키보드·마우스를 쓴다
    assert run("click", "--ref", "1")["code"] == "desktop_session_required"
    assert run("session", "start", "--purpose", "e2e")["ok"]

    # 깨지면: 입력칸·체크박스·버튼을 못 누르거나 마우스를 움직인다 (invoke 가 기본이어야 한다)
    typed = run("type", "--ref", str(ref_of("Name", role="edit")), "--text", "Hong Gildong")
    assert typed["ok"] and typed["transport"] == "invoke", typed
    toggled = run("click", "--ref", str(ref_of("Remember")))
    assert toggled["ok"] and toggled["transport"] == "invoke", toggled

    # 깨지면: 비밀번호가 명령줄에 남거나 결과에 찍힌다
    pw_ref = str(ref_of("Password", role="edit"))
    assert run("type", "--ref", pw_ref, "--text", SECRET)["code"] == "secret_requires_cred"
    hidden = run("type", "--ref", pw_ref, "--text-env", "PW_E2E", env={"PW_E2E": SECRET})
    assert hidden["ok"] and hidden["secret"] is True and SECRET not in json.dumps(hidden), hidden

    pressed = run("click", "--ref", str(ref_of("Next", role="button")))
    assert pressed["ok"] and pressed["screen_changed"] is True, pressed
    assert status_text() == f"step 1 name=Hong Gildong remember=True pwlen={len(SECRET)}"

    # 깨지면: 설치 버튼이 승인 없이 눌린다
    assert run("click", "--ref", str(ref_of("Install", role="button")))["code"] == "mutating_blocked"
    assert status_text().startswith("step 1")
    # status_text 의 find 가 번호를 새로 매겼다 — 누르기 직전에 다시 찾는다
    assert run("click", "--ref", str(ref_of("Install", role="button")), "--confirm-mutating")["ok"]
    assert status_text() == "installed"

    # 깨지면: 창을 닫는 키가 확인 없이 나가고, 닫힌 창의 번호로 다른 것을 누른다
    stale_ref = str(ref_of("Next", role="button"))
    assert run("press", "--key", "f4", "--mods", "alt", "--window", TITLE)["code"] == "mutating_blocked"
    assert run("press", "--key", "f4", "--mods", "alt", "--window", TITLE, "--confirm-mutating")["ok"]
    deadline = time.monotonic() + 10
    while fixture_window.poll() is None and time.monotonic() < deadline:
        time.sleep(0.2)
    assert fixture_window.poll() is not None, "Alt+F4 did not close the fixture window"
    assert run("click", "--ref", stale_ref)["code"] == "ref_stale"


def test_another_session_cannot_take_the_input(fixture_window):
    assert run("session", "start", "--purpose", "e2e")["ok"]
    # 깨지면: 두 agent 가 같은 마우스·키보드를 두고 싸운다
    other = run("session", "start", env={"LAUNCH_SESSION": "someone-else"})
    assert other["code"] == "desktop_busy" and other["holder"] == "desktop-e2e"
    assert run("click", "--ref", "1", env={"LAUNCH_SESSION": "someone-else"})["code"] == "desktop_busy"
