"""SessionEnd 훅 (#953) — 실제 launch_cli 를 띄우지 않고 검사한다."""
from __future__ import annotations

import importlib.util
import json
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


def test_hook_runs_release_all_with_session_env(monkeypatch, tmp_path):
    write_ledger(["mine"])
    seen = {}

    def fake_run(command, env, **kwargs):
        seen.update(command=command, session=env["LAUNCH_SESSION"])
    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    assert hook.main(json.dumps({"session_id": "mine"}), {}) == 0
    assert seen["session"] == "mine" and seen["command"][-3:] == ["device", "release", "--all"]


