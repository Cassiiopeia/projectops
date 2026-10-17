"""브라우저 생명주기 · 탭 소유권 · 로그인 인계 (#887 #878 #881) — 기기·브라우저 없이 돈다."""
from __future__ import annotations

import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.web import recovery, tabs  # noqa: E402
from pro_launch.commands.web.actions import login  # noqa: E402


# ── #887 자가 복구 ────────────────────────────────────────────────────────

def _locked_profile(tmp_path) -> Path:
    profile = tmp_path / ".browser-profile"
    profile.mkdir()
    # macOS·Linux 의 실제 모양: 대상이 없는 심볼릭 링크
    os.symlink("host-99999", profile / "SingletonLock")
    (profile / "SingletonCookie").write_text("x")
    return profile


def test_dead_pid_and_stale_lock_are_cleaned(monkeypatch, tmp_path):
    profile = _locked_profile(tmp_path)
    monkeypatch.setattr(recovery, "pid_alive", lambda pid: False)
    monkeypatch.setattr(recovery, "process_command_lines", lambda: "other --user-data-dir=/elsewhere")
    decision, recovered = recovery.recover_recorded_browser({"pid": 4242, "cdp": "http://127.0.0.1:1"}, profile)
    assert decision == "launch" and recovered == ["dead_pid", "stale_lock"]
    assert not os.path.lexists(profile / "SingletonLock") and not (profile / "SingletonCookie").exists()


def test_lock_is_kept_while_another_process_uses_the_profile(monkeypatch, tmp_path):
    profile = _locked_profile(tmp_path)
    monkeypatch.setattr(recovery, "process_command_lines", lambda: f"chrome --user-data-dir={profile}")
    decision, recovered = recovery.recover_recorded_browser({}, profile)
    assert decision == "launch" and recovered == []
    assert os.path.lexists(profile / "SingletonLock")


def test_hung_browser_is_closed_before_relaunch(monkeypatch, tmp_path):
    monkeypatch.setattr(recovery, "pid_alive", lambda pid: True)
    monkeypatch.setattr(recovery, "cdp_responds", lambda cdp, timeout=0: False)
    monkeypatch.setattr(recovery, "kill_browser", lambda pid, grace=0: False)
    monkeypatch.setattr(recovery, "process_command_lines", lambda: "")
    decision, recovered = recovery.recover_recorded_browser({"pid": 7, "cdp": "http://x"}, tmp_path)
    assert decision == "launch" and recovered == ["hung_browser"]


def test_cdp_probe_gives_up_on_a_silent_port():
    # 연결은 받지만 아무 응답도 안 하는 포트 — 멈춘 브라우저 흉내
    server = subprocess.Popen([sys.executable, "-c",
                               "import socket,time\ns=socket.socket();s.bind(('127.0.0.1',0));s.listen()\n"
                               "print(s.getsockname()[1],flush=True)\nc=s.accept();time.sleep(30)"],
                              stdout=subprocess.PIPE, text=True)
    try:
        port = int(server.stdout.readline())
        assert recovery.cdp_responds(f"http://127.0.0.1:{port}", timeout=0.5) is False
    finally:
        server.kill()


# ── #878 탭 소유권 ────────────────────────────────────────────────────────

class _TabPage:
    def __init__(self, url, tid):
        self.url, self.tid = url, tid

    def is_closed(self):
        return False


class _TabCtx:
    def __init__(self, pages):
        self.pages = pages


def _fake_target_ids(monkeypatch):
    monkeypatch.setattr(tabs, "target_id", lambda page: getattr(page, "tid", None))


def test_default_session_skips_tabs_owned_by_named_sessions(monkeypatch):
    _fake_target_ids(monkeypatch)
    mine, theirs = _TabPage("http://a/", "T1"), _TabPage("http://b/", "T2")
    state = {"tabs": {"edit-form": {"target_id": "T2"}}}
    assert tabs.default_tab_page(_TabCtx([mine, theirs]), state) is mine


def _no_session_env(monkeypatch):
    for var in (tabs.TAB_ENV_VAR, *tabs.SESSION_ENV_VARS):
        monkeypatch.delenv(var, raising=False)


def test_drift_warns_when_page_moved_without_this_session(monkeypatch):
    _fake_target_ids(monkeypatch)
    _no_session_env(monkeypatch)
    page = _TabPage("http://a/form?step=2", "T1")
    state = {}
    tabs.mark_tab(page, state)
    page.url = "http://a/form?step=3#x"   # 같은 화면 안의 쿼리·해시 변화는 경고하지 않는다
    assert tabs.drift_warning(page, state) is None
    page.url = "http://other.site/"
    warning = tabs.drift_warning(page, state)
    assert warning["code"] == "page_changed_by_other_session" and warning["previous_url"] == "http://a/form?step=2"


# ── #881 로그인 인계 ──────────────────────────────────────────────────────

class _Box:
    def __init__(self, page, selector, index=0):
        self.page, self.selector, self.index = page, selector, index

    @property
    def first(self):
        return _Box(self.page, self.selector, 0)

    def nth(self, index):
        return _Box(self.page, self.selector, index)

    def count(self):
        return self.page.box_counts.get(self.selector, 1)

    def wait_for(self, **_):
        return None

    def fill(self, value, timeout=None):
        if self.selector in self.page.broken:
            raise RuntimeError(f"fill failed with value {value}")
        self.page.filled.append((self.selector, self.index, value))

    def click(self, timeout=None):
        self.page.clicked.append(self.selector)
        self.page.url = self.page.url_after_submit

    def is_visible(self):
        return self.page.visible_text == self.selector


class _LoginPage:
    def __init__(self):
        self.url, self.url_after_submit = "http://local/login", "http://local/2fa"
        self.filled, self.clicked, self.box_counts, self.broken = [], [], {}, set()
        self.visible_text = None

    def locator(self, selector):
        return _Box(self, selector)

    def get_by_text(self, text):
        return _Box(self, text)

    def wait_for_load_state(self, *a, **k):
        return None

    def title(self):
        return "로그인"

    def wait_for_timeout(self, milliseconds):
        return None


def _login_args(**overrides) -> Namespace:
    base = dict(timeout=1, login_cred="staging", user_selector="#email", user_field=None,
                password_selector="#pw", password_field="password", submit_selector="#go",
                otp_env=None, otp_selector=None, until_url="/home", until_text=None,
                handoff_seconds=0, resume=False)
    base.update(overrides)
    return Namespace(**base)


def _fake_cred(monkeypatch, entry=None):
    entry = entry or {"email": "me@test.local", "password": "s3cret-pass"}
    monkeypatch.setattr(login, "load_cred", lambda name: (dict(entry, name=name), None))


def test_login_fills_and_hands_off_when_condition_not_met(monkeypatch):
    _fake_cred(monkeypatch)
    page = _LoginPage()
    payload = login.execute(page, _login_args(), {"headed": False})
    assert payload["code"] == "needs_user" and payload["needs_user"]["is_headed"] is False
    assert "--resume" in payload["next"] and "--until-url '/home'" in payload["next"]
    assert page.filled == [("#email", 0, "me@test.local"), ("#pw", 0, "s3cret-pass")]
    # 값은 결과 어디에도 없다
    assert "s3cret-pass" not in str(payload) and "me@test.local" not in str(payload)


def test_login_masks_secret_in_errors(monkeypatch):
    _fake_cred(monkeypatch)
    page = _LoginPage()
    page.broken.add("#pw")
    payload = login.execute(page, _login_args(), {})
    assert payload["code"] == "web_action_failed" and "s3cret-pass" not in payload["error"]


def test_connect_reports_hung_browser_without_waiting(monkeypatch):
    # 프로세스는 살아 있는데 CDP 무응답 → Playwright 연결 전에 browser_hung (#887)
    from pro_launch.commands.web import session as web_session
    monkeypatch.setattr(web_session, "pid_alive", lambda pid: True)
    monkeypatch.setattr(web_session, "cdp_responds", lambda cdp: False)
    monkeypatch.setattr(web_session, "require_playwright", lambda: (lambda: None, None))
    handles, failure = web_session.web_connect({"cdp": "http://127.0.0.1:1", "pid": 4242})
    assert handles is None and failure["code"] == "browser_hung" and "web open" in failure["next"]
