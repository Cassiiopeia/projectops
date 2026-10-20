"""SessionEnd 훅 (#953) — 실제 launch_cli 를 띄우지 않고 검사한다."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parents[3] / "hooks" / "pro_launch_session_end.py"
spec = importlib.util.spec_from_file_location("pro_launch_session_end", HOOK_PATH)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


def write_ledger(sessions: list[str]) -> None:
    """conftest 가 정한 상태 루트(PROJECTOPS_HOME)에 원장을 쓴다."""
    import os
    path = Path(os.environ["PROJECTOPS_HOME"]) / "launch" / "_machine" / "device-claims.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": 2, "devices": {"A": {"leases": [{"session": s} for s in sessions],
                                                                "settings": []}}, "waits": {}}), encoding="utf-8")


def test_hooks_json_registers_session_end_command():
    config = json.loads((HOOK_PATH.parent / "hooks.json").read_text(encoding="utf-8"))
    command = config["hooks"]["SessionEnd"][0]["hooks"][0]
    assert command["type"] == "command" and "pro_launch_session_end.py" in command["command"]


def test_hook_does_nothing_on_bad_stdin(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: called.append(a))
    assert hook.main("not json", {}) == 0
    assert hook.main("", {}) == 0
    assert called == []


def test_hook_skips_launch_when_session_has_no_leases(monkeypatch, tmp_path):
    write_ledger(["other"])
    called = []
    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: called.append(a))
    assert hook.main(json.dumps({"session_id": "mine"}), {}) == 0
    assert called == []


def test_hook_runs_release_all_with_session_env(monkeypatch, tmp_path):
    write_ledger(["mine"])
    seen = {}

    def fake_run(command, env, **kwargs):
        seen.update(command=command, session=env["LAUNCH_SESSION"])
    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    assert hook.main(json.dumps({"session_id": "mine"}), {}) == 0
    assert seen["session"] == "mine" and seen["command"][-3:] == ["device", "release", "--all"]


def test_hook_exits_zero_when_release_fails(monkeypatch, tmp_path):
    write_ledger(["mine"])

    def failing_run(*args, **kwargs):
        raise subprocess.TimeoutExpired("launch_cli", 25)
    monkeypatch.setattr(hook.subprocess, "run", failing_run)
    assert hook.main(json.dumps({"session_id": "mine"}), {}) == 0


def test_hook_reads_schema1_ledger():
    import os
    path = Path(os.environ["PROJECTOPS_HOME"]) / "launch" / "_machine" / "device-claims.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": 1, "claims": {"X": {"session": "mine"}}}), encoding="utf-8")
    assert hook.session_has_leases("mine") and not hook.session_has_leases("other")
