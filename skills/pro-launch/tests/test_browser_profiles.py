"""브라우저 프로필 고르기 · 로그인 기록 · 세션 종료 정리 (#956) — 브라우저 없이 상태 파일로 검사한다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands import tidy  # noqa: E402
from pro_launch.commands.web.actions import close  # noqa: E402
from pro_launch.runtime import browser_profiles  # noqa: E402
from pro_launch.runtime.browser import write_state  # noqa: E402


def result_of(capsys):
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def _browser_state(path: Path, session: str, tabs: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_state(path, {"pid": 4242, "cdp": "http://127.0.0.1:1", "opened_by_session": session,
                       "tab_marks": tabs or {}})
    return path


def test_session_end_closes_only_own_unshared_browsers(monkeypatch, capsys):
    shared = browser_profiles.shared_profiles_root()
    mine = _browser_state(shared / "a" / "browser.json", "me")
    shared_with_other = _browser_state(shared / "b" / "browser.json", "me", {"main@other": {}})
    others = _browser_state(shared / "c" / "browser.json", "other")
    monkeypatch.setenv("LAUNCH_SESSION", "me")
    monkeypatch.setattr(close, "pid_alive", lambda pid: True)
    killed = []
    monkeypatch.setattr(close, "kill_browser", lambda pid, grace=5.0: killed.append(pid) or False)
    close._close_session_browsers()
    data = result_of(capsys)
    assert [c["state_file"] for c in data["closed"]] == [str(mine)] and not mine.exists()
    assert shared_with_other.exists() and others.exists() and killed == [4242]
    assert data["kept"][0]["other_session_tabs"] == ["main@other"]


def test_tidy_keeps_profile_with_marks():
    row = {"is_browser_alive": False, "has_profile_marks": True, "classification": "scratch",
           "is_orphan_profile": True, "idle_days": 99, "has_data": False}
    assert tidy._decide_bucket_action(row, 7) == "keep:profile_has_marks"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 신호")
def test_kill_browser_sends_graceful_term_to_main_process_only(monkeypatch):
    """그룹 전체에 SIGTERM 을 보내면 Chrome 이 쿠키·로그인을 디스크에 쓰기 전에 끝난다 (실측)."""
    import signal

    from pro_launch.runtime import procs
    sent = []
    monkeypatch.setattr(procs.os, "kill", lambda pid, sig: sent.append(("kill", sig)))
    monkeypatch.setattr(procs.os, "killpg", lambda pid, sig: sent.append(("killpg", sig)))
    states = iter([True, False])
    monkeypatch.setattr(procs, "pid_alive", lambda pid: next(states, False))
    monkeypatch.setattr(procs.time, "sleep", lambda seconds: None)
    assert procs.kill_browser(4242, grace=1.0) is False
    assert sent[0] == ("kill", signal.SIGTERM)
    assert ("killpg", signal.SIGTERM) not in sent
