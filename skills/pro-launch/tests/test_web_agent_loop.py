"""agent 가 혼자 브라우저를 몰 수 있는가 (#825).

2026-10-10 Play Console 실측에서 겪은 것을 그대로 재현한다.
  · 링크가 아닌 셀을 눌렀는데 ok 가 나왔다           → click 이 무엇을 눌렀고 바뀌었는지 말해야 한다
  · 화면을 읽을 수 없어 선택자를 추측했다             → find / text
  · 추측한 클릭이 엉뚱한 메뉴로 튀었다                 → ref 로 정확히 누르고, 기대가 안 오면 실패
  · 관리 콘솔에서 되돌릴 수 없는 버튼을 누를 수 있었다 → --readonly
  · 떠 있던 브라우저가 있는데 open 이 실패했다        → reused
"""
from __future__ import annotations

import contextlib
import http.server
import os
import shutil
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_launch_cli import run_cli, _j, _repo  # noqa: E402
import launch_cli  # noqa: E402
from common import state as common_state  # noqa: E402

_UI = """<!doctype html><meta charset="utf-8"><title>목록</title>
<div role="row" onclick="location.href='/detail/44'"><span id="cell">10월 10, 2026</span><span>비공개 테스트 - Alpha</span></div>
<div role="row"><span>43 프로덕션</span><a href="/detail/43" aria-label="제출 세부정보 보기">arrow_right_alt</a></div>
<p id="plain">그냥 글자</p>
<a href="/next">다음 화면</a>
<a href="/history">제출 활동</a>
<button id="del" onclick="document.title='지워짐'">변경사항 삭제</button>
<button id="open" onclick="document.getElementById('more').hidden=false">펼치기</button>
<p id="more" hidden>숨은 내용 MORE_MARK</p>
""".encode()


def _page(path: str) -> bytes:
    if path.startswith("/next"):
        return '<!doctype html><meta charset="utf-8"><title>다음</title><p>NEXT_MARK</p>'.encode()
    if path.startswith("/history"):
        return '<!doctype html><meta charset="utf-8"><title>기록</title><p>HISTORY_MARK</p>'.encode()
    if path.startswith("/detail/"):
        return f'<!doctype html><meta charset="utf-8"><title>상세</title><p>DETAIL {path}</p>'.encode()
    return _UI


@contextlib.contextmanager
def _session(tmp_path):
    ok, _ = launch_cli._require_playwright()
    if ok is None:
        pytest.skip("Playwright 없음 — web setup 후 실행된다")

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = _page(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    proj = _repo(tmp_path, f"loop-{os.getpid()}", remote=None)
    state = common_state.state_dir("launch", proj)
    try:
        yield str(proj), f"http://127.0.0.1:{srv.server_port}/"
    finally:
        run_cli("web", "close", "--root", str(proj))
        srv.shutdown()
        shutil.rmtree(state, ignore_errors=True)


def web(r, *a):
    return _j(run_cli("web", *a, "--root", r)[1])


# ── 브라우저 없이 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", ["변경사항 삭제", "프로덕션으로 출시", "검토를 위해 변경사항 전송", "Publish", "Submit for review",
                                   "Delete app", "Roll out", "저장"])
def test_mutating_labels_are_recognised(label):
    assert launch_cli._is_mutating(label)


@pytest.mark.parametrize("label", ["취소", "확인", "다음", "필터 추가", "Details"])
def test_navigation_labels_are_not_mutating(label):
    assert not launch_cli._is_mutating(label)


@pytest.mark.parametrize("info", [
    {"tag": "a", "href": "/publishing/submission-activity", "text": "제출 활동"},
    {"tag": "a", "href": "/publishing", "text": "게시 개요"},
    {"tag": "div", "role": "row", "text": "44 비공개 테스트 - Alpha 검토 중"},
    {"tag": "div", "role": "tab", "text": "출시 대시보드"},
])
def test_links_tabs_and_rows_are_navigation_even_with_action_words(info):
    """Play Console 실측: 기록을 보는 링크 "제출 활동"을 문구만 보고 막으면 읽기 전용에서 아무것도 못 한다."""
    assert not launch_cli._is_mutating_target(info)


@pytest.mark.parametrize("info", [
    {"tag": "button", "text": "변경사항 삭제"},
    {"tag": "button", "text": "검토를 위해 변경사항 전송"},
    {"tag": "div", "role": "button", "aria": "Publish"},
    {"tag": "input", "text": "Submit"},
])
def test_buttons_with_action_words_are_mutating(info):
    assert launch_cli._is_mutating_target(info)


def test_every_response_has_a_string_summary(tmp_path):
    proj = _repo(tmp_path)
    d = _j(run_cli("web", "click", "--root", str(proj), "--ref", "1", home=tmp_path)[1])
    assert isinstance(d["summary"], str) and d["summary"], d


def test_click_needs_a_target():
    import argparse
    a = argparse.Namespace(ref=None, selector=None)
    assert launch_cli._web_click(None, a, {})["code"] == "target_required"


# ── 진짜 브라우저 ─────────────────────────────────────────────────────────

@pytest.mark.local_only
def test_find_then_click_by_ref_navigates_and_says_so(tmp_path):
    with _session(tmp_path) as (r, url):
        assert web(r, "open", "--url", url)["ok"]
        f = web(r, "find", "--text", "다음 화면")
        assert f["ok"] and f["items"][0]["href"] == "/next", f
        c = web(r, "click", "--ref", str(f["items"][0]["ref"]), "--expect-url", "/next")
        assert c["ok"] and c["changed"] is True and c["clicked"]["href"] == "/next", c
        assert "NEXT_MARK" in web(r, "text")["text"]


@pytest.mark.local_only
def test_text_in_a_cell_finds_the_clickable_row(tmp_path):
    """Play Console 실측: 날짜 셀 글자를 눌러도 행이 안 열렸다. 글자로 찾으면 그 글자를 품은 클릭 대상을 줘야 한다."""
    with _session(tmp_path) as (r, url):
        web(r, "open", "--url", url)
        f = web(r, "find", "--text", "10월 10, 2026")
        assert f["items"][0]["role"] == "row", f
        c = web(r, "click", "--ref", str(f["items"][0]["ref"]), "--expect-url", "/detail/44")
        assert c["ok"], c


@pytest.mark.local_only
def test_click_that_changes_nothing_is_reported(tmp_path):
    with _session(tmp_path) as (r, url):
        web(r, "open", "--url", url)
        c = web(r, "click", "--selector", "#plain")
        assert c["ok"] and c["changed"] is False and "web find" in c["next"], c
        bad = web(r, "click", "--selector", "#plain", "--expect-url", "/never", "--timeout", "2")
        assert bad["ok"] is False and bad["code"] == "expect_not_met", bad


@pytest.mark.local_only
def test_expect_text_waits_for_in_place_change(tmp_path):
    with _session(tmp_path) as (r, url):
        web(r, "open", "--url", url)
        c = web(r, "click", "--selector", "#open", "--expect-text", "MORE_MARK")
        assert c["ok"], c


@pytest.mark.local_only
def test_readonly_session_refuses_mutating_buttons(tmp_path):
    with _session(tmp_path) as (r, url):
        assert web(r, "open", "--url", url, "--readonly")["readonly"] is True
        f = web(r, "find", "--role", "button", "--text", "삭제")
        assert f["items"][0]["mutating"] is True, f
        blocked = web(r, "click", "--ref", str(f["items"][0]["ref"]))
        assert blocked["code"] == "mutating_blocked", blocked
        assert web(r, "assert", "--text", "그냥 글자")["ok"]
        assert web(r, "text")["title"] == "목록", "막았는데 눌렸다"
        # 기록을 보는 링크는 문구에 "제출"이 있어도 읽기 전용에서 열린다 (Play Console 실측)
        f2 = web(r, "find", "--text", "제출 활동")
        assert f2["items"][0]["mutating"] is False, f2
        assert web(r, "click", "--ref", str(f2["items"][0]["ref"]), "--expect-url", "/history")["ok"]


@pytest.mark.local_only
def test_confirm_mutating_lets_an_approved_click_through(tmp_path):
    with _session(tmp_path) as (r, url):
        web(r, "open", "--url", url, "--readonly")
        c = web(r, "click", "--selector", "#del", "--confirm-mutating")
        assert c["ok"] and c["title"] == "지워짐", c


@pytest.mark.local_only
def test_stale_ref_is_refused_after_navigation(tmp_path):
    with _session(tmp_path) as (r, url):
        web(r, "open", "--url", url)
        f = web(r, "find", "--text", "펼치기")
        web(r, "goto", "--url", url + "next")
        stale = web(r, "click", "--ref", str(f["items"][0]["ref"]))
        assert stale["code"] == "ref_stale" and "web find" in stale["next"], stale


@pytest.mark.local_only
def test_open_twice_reuses_the_live_browser(tmp_path):
    with _session(tmp_path) as (r, url):
        first = web(r, "open", "--url", url)
        again = web(r, "open", "--url", url + "next")
        assert again["ok"] and again["reused"] is True and again["pid"] == first["pid"], again
        assert again["title"] == "다음"


@pytest.mark.local_only
def test_real_link_comes_before_the_row_that_wraps_it(tmp_path):
    """Play Console 실측: 행과 그 안의 링크가 둘 다 걸리면 링크가 먼저여야 첫 후보로 바로 열린다."""
    with _session(tmp_path) as (r, url):
        web(r, "open", "--url", url)
        f = web(r, "find", "--text", "arrow_right_alt")
        assert f["items"][0]["tag"] == "a" and f["items"][0]["href"] == "/detail/43", f
        assert web(r, "click", "--ref", "1", "--expect-url", "/detail/43")["ok"]


def test_doctor_reports_an_abandoned_browser(tmp_path):
    """3일 묵은 브라우저가 살아 있었는데 아무도 몰랐다 (Play Console 실측). 살아 있는 pid 로 흉내 낸다."""
    proj = _repo(tmp_path)
    st = launch_cli._web_state_path(proj)
    launch_cli._write_web_state(st, {"cdp": "http://127.0.0.1:1", "pid": os.getpid(),
                                     "opened_at": "2026-10-06 22:09:48", "last_used": "2026-10-06 22:10:00"})
    b = launch_cli._open_browser_status(st)
    assert b["alive"] and b["stale"] and "web close" in b["hint"], b
    launch_cli._write_web_state(st, {"pid": os.getpid(), "last_used": __import__("time").strftime("%Y-%m-%d %H:%M:%S")})
    assert launch_cli._open_browser_status(st)["stale"] is False


def test_help_lists_the_reading_and_checking_options():
    _, out, err = run_cli("web", "--help")
    for a in ("find", "text", "--ref", "--expect-url", "--expect-text", "--readonly", "--confirm-mutating"):
        assert a in out + err, f"{a} 가 web --help 에 없다"
