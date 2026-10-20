"""디스패처 소유 게이트 (#953) — 모든 기기 동작이 선언을 갖고, 남의 기기 조작은 한 곳에서 거부된다."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands import app as app_command  # noqa: E402
from pro_launch.commands import device as device_command  # noqa: E402
from pro_launch.registry import DEVICE_USES  # noqa: E402
from pro_launch.runtime import device_claims, device_gate, output  # noqa: E402

UDID = "3F328F1A-16D1-453B-A0D3-94CDC21C4189"


@pytest.fixture(autouse=True)
def fake_device(monkeypatch):
    monkeypatch.setattr(device_gate, "pick_device", lambda want: ("ios", want or UDID, {}))
    monkeypatch.setattr(device_claims, "current_host", lambda: None)
    monkeypatch.setattr(output, "PENDING_RESPONSE_FIELDS", {})


def app_args(tmp_path, action, **values):
    base = dict(action=action, root=str(tmp_path), device=UDID, yes=False, pkg=None, shot=None)
    base.update(values)
    return argparse.Namespace(**base)


def result_of(capsys):
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_every_app_action_declares_device_use():
    missing = [name for name, action in app_command.ACTIONS.items() if action.device_use not in DEVICE_USES]
    assert missing == []


def test_every_device_action_declares_device_use():
    assert set(device_command.DEVICE_USE_BY_ACTION) == set(device_command._RUNNERS)
    assert set(device_command.DEVICE_USE_BY_ACTION.values()) <= set(DEVICE_USES)


def test_tap_on_other_sessions_device_is_refused_without_yes(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LAUNCH_SESSION", "owner")
    device_claims.claim_device(UDID, "/r")
    monkeypatch.setenv("LAUNCH_SESSION", "intruder")
    ran = []
    monkeypatch.setitem(app_command.ACTIONS, "tap",
                        app_command.ACTIONS["tap"].__class__(name="tap", run=lambda args: ran.append(1) or 0,
                                                             device_use="mutate"))
    app_command.cmd_app(app_args(tmp_path, "tap"))
    assert result_of(capsys)["code"] == "device_owned_by_other" and ran == []
    app_command.cmd_app(app_args(tmp_path, "tap", yes=True))
    assert ran == [1]


def test_shot_on_other_sessions_device_warns_but_runs(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LAUNCH_SESSION", "owner")
    device_claims.claim_device(UDID, "/r")
    monkeypatch.setenv("LAUNCH_SESSION", "viewer")
    monkeypatch.setitem(app_command.ACTIONS, "shot",
                        app_command.ACTIONS["shot"].__class__(name="shot", device_use="read",
                                                              run=lambda args: output.out({"action": "shot"})))
    app_command.cmd_app(app_args(tmp_path, "shot"))
    data = result_of(capsys)
    assert data["action"] == "shot" and data["device_owned_by_other"]["session"] == "owner"


def test_tap_refreshes_last_used_of_own_lease(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LAUNCH_SESSION", "me")
    device_claims.claim_device(UDID, "/r")
    before = device_claims.device_owner(UDID)["last_used"]
    time.sleep(0.01)
    monkeypatch.setitem(app_command.ACTIONS, "tap",
                        app_command.ACTIONS["tap"].__class__(name="tap", run=lambda args: 0, device_use="mutate"))
    app_command.cmd_app(app_args(tmp_path, "tap"))
    assert device_claims.device_owner(UDID)["last_used"] > before


def test_no_action_module_records_ownership_itself():
    actions_folder = SCRIPTS / "pro_launch" / "commands" / "app" / "actions"
    offenders = [p.name for p in actions_folder.glob("*.py")
                 if "device_use_fields" in p.read_text(encoding="utf-8") or "touch_device" in p.read_text(encoding="utf-8")]
    assert offenders == []
