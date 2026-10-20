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


def test_find_agent_host_skips_own_command_even_if_it_looks_like_a_host(monkeypatch):
    monkeypatch.delenv(agent_hosts.HOST_PID_ENV_VAR, raising=False)
    rows = [{"pid": 5, "ppid": 1, "elapsed_seconds": 1, "command": "/Applications/Cursor.app/x python3 launch_cli.py"},
            {"pid": 1, "ppid": 0, "elapsed_seconds": 9, "command": "/sbin/launchd"}]
    assert agent_hosts.find_agent_host(rows, start_pid=5) is None


def test_find_agent_host_honors_env_override(monkeypatch):
    monkeypatch.setenv(agent_hosts.HOST_PID_ENV_VAR, "20")
    assert agent_hosts.find_agent_host(_rows(), start_pid=30)["pid"] == 20


def test_find_agent_host_returns_none_without_match(monkeypatch):
    monkeypatch.delenv(agent_hosts.HOST_PID_ENV_VAR, raising=False)
    rows = [r for r in _rows() if r["pid"] != 10] + [{"pid": 10, "ppid": 1, "elapsed_seconds": 1, "command": "bash"}]
    assert agent_hosts.find_agent_host(rows, start_pid=30) is None


def test_node_launched_and_windows_hosts_are_recognized():
    assert agent_hosts.is_agent_host_command("node /usr/local/lib/node_modules/codex/bin/codex.js exec")
    assert agent_hosts.is_agent_host_command(r"C:\Users\a\AppData\Local\claude.exe --resume")
    assert not agent_hosts.is_agent_host_command("/bin/zsh -c claude-like-script")


def test_is_host_alive_false_when_pid_reused():
    host = {"pid": 10, "started_at": 0.0}
    assert agent_hosts.is_host_alive(host, _rows()) is False


def test_is_host_alive_true_for_same_process():
    host = agent_hosts.find_agent_host(_rows(), start_pid=30)
    assert agent_hosts.is_host_alive(host, _rows()) is True


def test_is_host_alive_false_when_gone_and_none_without_host():
    assert agent_hosts.is_host_alive({"pid": 777, "started_at": 1.0}, _rows()) is False
    assert agent_hosts.is_host_alive(None, _rows()) is None


def test_is_host_alive_without_table_uses_single_pid_lookup(monkeypatch):
    monkeypatch.setattr(agent_hosts.procs, "pid_alive", lambda pid: pid == 10)
    monkeypatch.setattr(agent_hosts.procs, "read_process", lambda pid: None)
    assert agent_hosts.is_host_alive({"pid": 10, "started_at": 1.0}) is None
    assert agent_hosts.is_host_alive({"pid": 11, "started_at": 1.0}) is False


def test_read_process_reads_this_process():
    import os
    row = agent_hosts.procs.read_process(os.getpid())
    assert row is None or row["pid"] == os.getpid()
