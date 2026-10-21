"""agent 호스트 판별 (#953) — 실제 ps 없이 가짜 프로세스 표로 검사한다."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.runtime import agent_hosts  # noqa: E402


def _rows():
    return [{"pid": 30, "ppid": 20, "elapsed_seconds": 1, "command": "python3 /Users/x/.cursor/skills/launch_cli.py"},
            {"pid": 20, "ppid": 10, "elapsed_seconds": 5, "command": "/bin/zsh -c source snapshot.sh"},
            {"pid": 10, "ppid": 1, "elapsed_seconds": 100, "command": "claude --dangerously-skip-permissions"},
            {"pid": 1, "ppid": 0, "elapsed_seconds": 9999, "command": "/sbin/launchd"}]


def test_find_agent_host_walks_parents_to_first_matching_command(monkeypatch):
    monkeypatch.delenv(agent_hosts.HOST_PID_ENV_VAR, raising=False)
    host = agent_hosts.find_agent_host(_rows(), start_pid=30)
    assert host["pid"] == 10
    assert host["started_at"] is not None


def test_is_host_alive_false_when_pid_reused():
    host = {"pid": 10, "started_at": 0.0}
    assert agent_hosts.is_host_alive(host, _rows()) is False


