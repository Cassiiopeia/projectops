"""web 브라우저 위생 · 시간 상한 · 계약 (#921 · #930 · #931).

브라우저 없이 도는 것: 버려진 브라우저 판정 · 테스트 정리 안전망 · 요청 주소 정리 · 저장 값 · timeout 상한 · 역할 별칭.
실제 브라우저가 필요한 것만 local_only.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_cleanup import browser_pids_under, close_browser_for_test, sweep_browsers_under  # noqa: E402
from test_launch_cli import _j, _repo, run_cli  # noqa: E402
from pro_launch.commands.web import options as web_options  # noqa: E402
from pro_launch.commands.web import request_capture, saved_values, targets  # noqa: E402
from pro_launch.runtime import browser as rt_browser  # noqa: E402
from pro_launch.runtime.procs import kill_browser, pid_alive  # noqa: E402


def _fake_browser(profile: Path) -> subprocess.Popen:
    """Chrome 처럼 보이는 명령줄을 가진 잠자는 프로세스 (--remote-debugging-port · --user-data-dir)"""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", "--remote-debugging-port=1",
         f"--user-data-dir={profile}"], start_new_session=True)
    # 죽자마자 거둔다 — 안 거두면 좀비로 남아 pid_alive 가 계속 True 다 (진짜 고아는 PPID 1 이 거둔다)
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc


# ── 테스트 정리 안전망 (#921) ──────────────────────────────────────────────

def test_cleanup_helper_kills_the_recorded_pid_when_web_close_fails(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    proc = _fake_browser(tmp_path / "p" / ".browser-profile")
    try:
        (state_dir / "browser.json").write_text(json.dumps({"pid": proc.pid}))
        # web close 가 아무것도 못 끈 상황 — run_cli 를 아무 일도 안 하는 가짜로 바꾼다
        close_browser_for_test(lambda *a, **k: (1, "", ""), tmp_path, state_dir)
        proc.wait(timeout=5)
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            kill_browser(proc.pid, grace=0.5)


def test_sweep_kills_only_browsers_under_the_given_folder(tmp_path):
    inside = _fake_browser(tmp_path / "mine" / ".browser-profile")
    outside = _fake_browser(Path("/private/var/outside-sweep-test") / ".browser-profile")
    try:
        time.sleep(0.3)
        killed = sweep_browsers_under(tmp_path)
        assert inside.pid in killed and outside.pid not in killed
        inside.wait(timeout=5)
        assert outside.poll() is None
    finally:
        for proc in (inside, outside):
            if proc.poll() is None:
                kill_browser(proc.pid, grace=0.5)


# ── 버려진 브라우저 판정 (#921) ────────────────────────────────────────────

def test_stale_browser_is_found_when_profile_is_gone_and_live_one_is_kept(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".projectops"
    monkeypatch.setenv("PROJECTOPS_HOME", str(home))
    gone_profile = home / "launch" / "gone" / ".browser-profile"      # 폴더를 만들지 않는다 = 프로필 사라짐
    live_profile = home / "launch" / "live" / ".browser-profile"
    live_profile.mkdir(parents=True)
    gone = _fake_browser(gone_profile)
    live = _fake_browser(live_profile)
    foreign = _fake_browser(tmp_path / "users-own-chrome-profile")    # 우리 프로필이 아니면 보지도 않는다
    try:
        (live_profile.parent / "browser.json").write_text(json.dumps(
            {"pid": live.pid, "last_used": time.strftime("%Y-%m-%d %H:%M:%S")}))
        time.sleep(0.3)
        found = rt_browser.find_stale_browsers()
        stale_pids = {entry["pid"]: entry["reasons"] for entry in found["stale"]}
        kept_pids = {entry["pid"] for entry in found["kept"]}
        assert stale_pids.get(gone.pid) == ["profile_gone"]
        assert live.pid in kept_pids
        assert foreign.pid not in stale_pids and foreign.pid not in kept_pids
    finally:
        for proc in (gone, live, foreign):
            kill_browser(proc.pid, grace=0.5)


def test_close_stale_dry_run_reports_without_killing(tmp_path):
    root = _repo(tmp_path, remote=None)
    home = tmp_path / "ph" / ".projectops"
    gone = _fake_browser(home / "launch" / "gone" / ".browser-profile")
    try:
        time.sleep(0.3)
        env = {"PROJECTOPS_HOME": str(home)}
        rc, out, _ = run_cli("web", "close", "--stale", "--dry-run", "--root", str(root), env_extra=env)
        data = _j(out)
        assert data["ok"] is True and data["dry_run"] is True
        assert any(entry["pid"] == gone.pid for entry in data["stale"]) and gone.poll() is None
        _, out, _ = run_cli("web", "close", "--stale", "--root", str(root), env_extra=env)
        assert any(entry["pid"] == gone.pid for entry in _j(out)["closed"])
        gone.wait(timeout=5)
    finally:
        if gone.poll() is None:
            kill_browser(gone.pid, grace=0.5)


# ── 계약 (#930 · #931) ─────────────────────────────────────────────────────

def test_timeout_in_milliseconds_is_rejected_before_touching_the_browser(tmp_path):
    root = _repo(tmp_path, remote=None)
    rc, out, _ = run_cli("web", "type", "--selector", "#x", "--text", "a", "--timeout", "3000", "--root", str(root))
    data = _j(out)
    assert data["code"] == "timeout_too_large" and data["maximum_seconds"] == web_options.MAXIMUM_TIMEOUT_SECONDS
    assert "초" in data["hint"]


def test_failure_without_a_browser_keeps_the_main_keys(tmp_path):
    root = _repo(tmp_path, remote=None)
    data = _j(run_cli("web", "find", "--text", "x", "--root", str(root))[1])
    assert data["code"] == "browser_not_open" and "url" in data and data["url"] is None


def test_textbox_role_maps_to_plain_inputs():
    assert targets.role_selector("textbox") == targets.ROLE_SELECTORS["input"]
    assert "input:not([type=hidden])" in targets.role_selector("searchbox")
    assert targets.role_selector("link") is None


def test_request_urls_hide_secret_query_values_and_fragments():
    cleaned = request_capture.clean_url("https://x.test/save?token=abc&page=2#frag")
    assert "abc" not in cleaned and "page=2" in cleaned and "#" not in cleaned
    assert len(request_capture.clean_url("https://x.test/" + "a" * 500)) <= request_capture.MAXIMUM_URL_CHARS + 1


def test_saved_value_is_private_and_never_returned(tmp_path):
    root = _repo(tmp_path, remote=None)
    summary = saved_values.save_value(root, "CLIENT_SECRET", "it's a $ecret")
    assert "it's" not in json.dumps(summary) and summary["length"] == 13
    path = Path(summary["env_file"])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert saved_values.read_saved_values(root)["CLIENT_SECRET"] == "it's a $ecret"
    assert not saved_values.is_valid_env_name("1BAD") and saved_values.is_valid_env_name("OK_1")


def test_selector_syntax_error_detection_is_shared():
    assert targets.is_selector_syntax_error("Unexpected token \"=\" while parsing css selector")
    assert not targets.is_selector_syntax_error("Timeout 4000ms exceeded")
