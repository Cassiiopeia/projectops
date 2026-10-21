"""브라우저 생명주기 · 탭 소유권 · 로그인 인계 (#887 #878 #881) — 기기·브라우저 없이 돈다."""
from __future__ import annotations

import os
import sys
from argparse import Namespace
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.web import recovery  # noqa: E402
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

