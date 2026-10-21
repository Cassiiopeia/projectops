"""raw 기기 명령 차단 훅 (#954) — 막을 것만 막고 글자 검색·일반 명령은 통과시킨다."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).resolve().parents[3] / "hooks" / "pro_launch_raw_device_guard.py"
spec = importlib.util.spec_from_file_location("pro_launch_raw_device_guard", HOOK_PATH)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def decision_of(command: str, capsys, tool_name: str = "Bash") -> str | None:
    assert guard.main(json.dumps({"tool_name": tool_name, "tool_input": {"command": command}})) == 0
    printed = capsys.readouterr().out.strip()
    return json.loads(printed)["hookSpecificOutput"]["permissionDecision"] if printed else None


@pytest.mark.parametrize("command", [
    "cd app && xcrun simctl delete 5CFC4B8B-5245-4442-B4DC-37327092CCFD",
    "ANDROID_HOME=/x emulator -avd QA -wipe-data -no-window",
    "adb -s emulator-5554 emu kill; echo done",
])
def test_device_lifecycle_commands_are_denied(command, capsys):
    assert decision_of(command, capsys) == "deny"


@pytest.mark.parametrize("command", [
    "grep -rn \"simctl create\" skills/",
    "xcrun simctl boot 5CFC4B8B-5245-4442-B4DC-37327092CCFD",
    "PRO_LAUNCH_ALLOW_RAW=1 xcrun simctl delete ABC",
])
def test_other_commands_pass(command, capsys):
    assert decision_of(command, capsys) is None
