"""브라우저 프로필 고르기 · 로그인 기록 · 세션 종료 정리 (#956) — 브라우저 없이 상태 파일로 검사한다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands import tidy  # noqa: E402
from pro_launch.commands import web as web_command  # noqa: E402
from pro_launch.commands.web.actions import close, profile  # noqa: E402
from pro_launch.runtime import browser_profiles, device_marks  # noqa: E402
from pro_launch.runtime.browser import write_state  # noqa: E402


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.delenv(browser_profiles.PROFILE_ENV_VAR, raising=False)
    project = tmp_path / "project"
    project.mkdir()
    return project


def result_of(capsys):
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_repo_profile_is_default_and_choice_is_remembered(root):
    assert browser_profiles.chosen_profile(root) is None
    repo_state = browser_profiles.web_state_path(root)
    browser_profiles.choose_profile(root, "work")
    assert browser_profiles.chosen_profile(root) == "work"
    shared_state = browser_profiles.web_state_path(root)
    assert shared_state.parent == browser_profiles.shared_profiles_root() / "work" and shared_state != repo_state
    browser_profiles.choose_profile(root, "repo")
    assert browser_profiles.chosen_profile(root) is None


def test_env_var_overrides_remembered_choice(root, monkeypatch):
    browser_profiles.choose_profile(root, "work")
    monkeypatch.setenv(browser_profiles.PROFILE_ENV_VAR, "personal")
    assert browser_profiles.chosen_profile(root) == "personal"
    monkeypatch.setenv(browser_profiles.PROFILE_ENV_VAR, "repo")
    assert browser_profiles.chosen_profile(root) is None


def test_need_picks_repo_profile_first_then_shared(root):
    browser_profiles.choose_profile(root, "work")   # 폴더를 만든다
    browser_profiles.choose_profile(root, None)
    device_marks.add_mark(browser_profiles.profile_mark_key(root, "work"), "login", "google")
    assert browser_profiles.profile_with_marks(root, ["login:google"]) == "work"
    device_marks.add_mark(browser_profiles.profile_mark_key(root, "repo"), "login", "google")
    assert browser_profiles.profile_with_marks(root, ["login:google"]) == "repo"
    assert browser_profiles.profile_with_marks(root, ["login:kakao"]) is None


def test_open_choice_errors_and_selection(root):
    no_match = web_command.apply_profile_choice(argparse.Namespace(profile=None, need=["login:kakao"]), root)
    assert no_match["code"] == "no_matching_profile"
    bad = web_command.apply_profile_choice(argparse.Namespace(profile="../evil", need=None), root)
    assert bad["code"] == "bad_args"
    assert web_command.apply_profile_choice(argparse.Namespace(profile="work", need=None), root) is None
    assert browser_profiles.chosen_profile(root) == "work"


def test_web_profile_mark_list_unmark(root, capsys):
    def run(operation, **values):
        base = dict(operation=operation, root=str(root), profile=None, kind=None, mark_name=None, note=None)
        base.update(values)
        profile._web_profile(argparse.Namespace(**base))
        return result_of(capsys)
    assert run("mark", kind="login")["code"] == "args_required"
    marked = run("mark", kind="login", mark_name="github", note="회사 계정")
    assert marked["key"].startswith("browser-profile:repo:")
    listed = run("list")
    assert listed["current"] == "repo" and listed["profiles"][0]["marks"][0]["label"] == "login:github"
    assert run("use", profile="work")["current"] == "work"
    assert run("unmark", kind="login", mark_name="github", profile="repo")["removed"] is True


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


def test_session_end_hook_sees_browsers_of_the_session():
    import importlib.util
    hook_path = Path(__file__).resolve().parents[3] / "hooks" / "pro_launch_session_end.py"
    spec = importlib.util.spec_from_file_location("pro_launch_session_end_browsers", hook_path)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    _browser_state(browser_profiles.shared_profiles_root() / "a" / "browser.json", "me")
    assert hook.session_has_browsers("me") and not hook.session_has_browsers("nobody")


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
