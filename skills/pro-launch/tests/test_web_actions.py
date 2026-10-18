"""web 의 폼 읽기 · 조작 동작과 동작별 도움말 (#888 · #891 · #892 · #896 · #899).

108개 세션 분석에서 agent 가 `web` 을 두고 날 CDP 스크립트를 654번 썼다 — 기능이 없어서였다.
여기서 지키는 것:
  · 폼을 읽는다(inspect) · 줄만 골라 읽는다(text --grep)
  · 고르기 · 체크 · 키 · 올리기 · 대화상자 · 내려받기
  · 비활성 요소는 타임아웃까지 기다리지 않고 바로 element_disabled
  · 추측한 선택자가 빗나가면 4초 안에 후보(candidates)와 --ref 안내를 돌려준다
  · `web <동작> --help` 는 그 동작의 옵션만, 안 받는 옵션은 bad_args 로 거절
"""
from __future__ import annotations

import argparse
import contextlib
import http.server
import os
import shutil
import sys
import threading
from pathlib import Path

import pytest

from browser_cleanup import close_browser_for_test

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_launch_cli import _j, _repo, run_cli  # noqa: E402
from pro_launch import registry  # noqa: E402
from pro_launch.commands.web import candidates as web_candidates  # noqa: E402
from pro_launch.commands.web import element as web_element  # noqa: E402
from pro_launch.commands.web import session as web_session  # noqa: E402
from pro_launch.commands.web.actions import dialog as web_dialog  # noqa: E402
from pro_launch.commands.web.actions import download as web_download  # noqa: E402
from pro_launch.commands.web.actions import select as web_select  # noqa: E402
from pro_launch.commands.web.actions import text as web_text  # noqa: E402
from pro_launch.runtime import browser as rt_browser  # noqa: E402
from common import state as common_state  # noqa: E402


# ── 동작별 도움말 · 옵션 거절 (#896) ─────────────────────────────────────

def test_action_help_shows_only_its_own_options():
    _, out, _ = run_cli("web", "type", "--help")
    assert "--text-env" in out and "--selector" in out and "예:" in out
    for foreign in ("--expect-url", "--max-side", "--headed", "--match"):
        assert foreign not in out, f"{foreign} 가 web type --help 에 보인다"


def test_option_of_another_action_is_rejected_with_the_valid_list(tmp_path):
    rc, out, _ = run_cli("web", "type", "--root", str(_repo(tmp_path)), "--selector", "#x",
                         "--expect-url", "/home", home=tmp_path)
    d = _j(out)
    assert rc != 0 and d["code"] == "bad_args", d
    assert "--expect-url" in d["error"] and "--text-env" in d["error"], d


def test_web_help_lists_every_action_with_its_options():
    _, out, _ = run_cli("web", "--help")
    for word in ("inspect", "select", "check", "press", "hover", "dialog", "download", "--grep", "--near"):
        assert word in out, f"{word} 가 web --help 에 없다"


# 다른 스킬이 문서대로 부르는 조합 — 하나라도 bad_args 면 그 스킬이 깨진다
CALLER_COMBINATIONS = [
    ["open", "--url", "http://x", "--headed", "--readonly", "--ignore-cert-errors", "--timeout", "5"],
    ["goto", "--url", "http://x"], ["text"], ["text", "--selector", "main", "--max-chars", "100"],
    ["find", "--text", "로그인", "--role", "button", "--selector", "a", "--limit", "5"],
    ["click", "--ref", "1", "--expect-url", "/home", "--confirm-mutating", "--timeout", "2"],
    ["click", "--selector", "#go", "--expect-text", "x"],
    ["type", "--selector", "#v", "--text", "a"], ["type", "--selector", "#v", "--cred", "g", "--cred-field", "account"],
    ["type", "--selector", "#v", "--text-env", "PW"],
    ["shot", "--out", "a", "--full", "--keep-format", "--selector", "#a", "--max-side", "0", "--quality", "80"],
    ["assert", "--url", "/home", "--text", "환영", "--selector", "#a"], ["console"], ["close"],
    ["route", "--match", "**/api*", "--status", "200", "--body", "[]"], ["route", "--clear"],
    ["route", "--match", "**/api*", "--delay", "5000", "--body-text", "x"],
    ["viewport", "--preset", "mobile"], ["viewport", "--clear"], ["setup", "--force"],
]


@pytest.mark.parametrize("argv", CALLER_COMBINATIONS, ids=lambda a: " ".join(a[:2]))
def test_documented_caller_combinations_still_parse(argv):
    from pro_launch.cli import build_parser
    args = build_parser().parse_args(["web", *argv, "--root", "."])
    assert args.action == argv[0]
    # 선언하지 않은 공통 옵션도 기본값으로 속성은 있다 — 디스패처가 그대로 읽는다
    assert hasattr(args, "text_env") and hasattr(args, "ref")


def test_unknown_shared_option_name_is_a_developer_error():
    parser = argparse.ArgumentParser()
    bad = {"x": registry.Action(name="x", run=lambda p, a, s: {}, options=("nope",))}
    with pytest.raises(ValueError, match="nope"):
        registry.add_action_parsers(parser, bad, {"root": lambda p: p.add_argument("--root")})


def test_action_without_options_stays_permissive():
    """app 은 동작별로 나누지 않았다 — options 를 안 적으면 공통 옵션을 전부 받는다."""
    parser = argparse.ArgumentParser()
    acts = {"x": registry.Action(name="x", run=lambda p, a, s: {})}
    registry.add_action_parsers(parser, acts, {"root": lambda p: p.add_argument("--root"),
                                               "url": lambda p: p.add_argument("--url")})
    assert parser.parse_args(["x", "--url", "u", "--root", "r"]).url == "u"


# ── text --grep (#891) ────────────────────────────────────────────────────

def test_grep_returns_matching_lines_with_context_and_count():
    lines = ["a", "b", "Error one", "c", "d", "e", "f", "error two", "g"]
    text, count = web_text.grep_lines(lines, "ERROR", 1)
    assert count == 2
    assert text.split("\n") == ["b", "Error one", "c", "…", "f", "error two", "g"]


def test_grep_is_not_a_regex():
    assert web_text.grep_lines(["a.b", "axb"], "a.b", 0) == ("a.b", 1)


# ── select · download 의 순수 규칙 ────────────────────────────────────────

def test_pick_option_prefers_value_then_label():
    options = [{"value": "seoul", "label": "서울", "selected": False},
               {"value": "busan", "label": "Busan", "selected": True}]
    assert web_select.pick_option(options, "서울")["value"] == "seoul"
    assert web_select.pick_option(options, "busan")["value"] == "busan"
    assert web_select.pick_option(options, " BUSAN ")["value"] == "busan"
    assert web_select.pick_option(options, "daegu") is None


def test_download_path_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOT_DIR", str(tmp_path / "run"))
    root = tmp_path
    assert web_download.download_path(root, None, "r.csv") == tmp_path / "run" / "r.csv"
    assert web_download.download_path(root, "report", "r.csv").name == "report.csv"
    explicit = tmp_path / "x" / "y.bin"
    assert web_download.download_path(root, str(explicit), "r.csv") == explicit
    (tmp_path / "run" / "r.csv").write_text("old")
    assert web_download.download_path(root, None, "r.csv").name != "r.csv", "덮어쓰면 안 된다"


# ── 비활성 요소 (#888) — 가짜 페이지 ──────────────────────────────────────

class _FakeLocator:
    def __init__(self, info):
        self.info = info
        self.first = self

    def count(self):
        return 1 if self.info else 0

    def evaluate(self, js):
        return self.info


class _FakePage:
    url = "http://local/"

    def __init__(self, info, scanned_items=None, frame_count=1):
        self._info = info
        self._scanned_items = scanned_items or []
        self.frames = [object()] * frame_count

    def locator(self, selector):
        return _FakeLocator(self._info)

    def evaluate(self, js, options):
        # 후보 스캔(INSPECT_JS) 흉내 — 화면 순서대로 돌려준다
        return {"items": self._scanned_items[:options["limit"]]}


def _args(**kw):
    base = {"ref": None, "selector": "#b", "timeout": 1, "confirm_mutating": False}
    return argparse.Namespace(**{**base, **kw})


def test_visible_disabled_target_fails_immediately():
    page = _FakePage({"tag": "button", "text": "다음", "visible": True, "disabled": True})
    _el, _info, failure = web_element.locate_target(page, _args(), {}, "click")
    assert failure["code"] == "element_disabled" and failure["target"]["text"] == "다음", failure


def test_hidden_disabled_target_is_not_judged_yet():
    page = _FakePage({"tag": "button", "text": "다음", "visible": False, "disabled": True})
    element, _info, failure = web_element.locate_target(page, _args(), {}, "click")
    assert failure is None and element is not None


def test_readonly_session_blocks_mutating_target_unless_confirmed():
    page = _FakePage({"tag": "button", "text": "삭제", "visible": True, "disabled": False})
    assert web_element.locate_target(page, _args(), {"readonly": True}, "check")[2]["code"] == "mutating_blocked"
    assert web_element.locate_target(page, _args(confirm_mutating=True), {"readonly": True}, "check")[2] is None


# ── 빗나간 선택자 → 후보 · 짧은 기본 대기 (#888) ───────────────────────────

_SCANNED = [
    {"ref": 1, "role": "link", "tag": "a", "label": "홈", "href": "/"},
    {"ref": 2, "role": "input", "tag": "input", "label": "검색", "name": "q", "value": "지난 검색어"},
    {"ref": 3, "role": "input", "tag": "input", "label": "이메일 주소", "id": "email", "name": "email",
     "value": "me@private.example"},
    {"ref": 4, "role": "button", "tag": "button", "label": "Next", "disabled": True},
    {"ref": 5, "role": "button", "tag": "button", "label": "Sign in"},
]


def test_selector_words_drop_css_syntax():
    assert web_candidates.selector_words("button:has-text('Next')") == ["button", "next"]
    assert web_candidates.selector_words("input[type=email]") == ["input", "email"]
    assert web_candidates.selector_words("text=로그인") == ["로그인"]
    assert "a" in web_candidates.selector_words("a[href*=login]")


def test_candidates_rank_by_guessed_selector_and_hide_values():
    ranked = web_candidates.rank_candidates(_SCANNED, "input[type=email]", "type")
    assert ranked[0]["ref"] == 3, ranked
    assert all("value" not in c for c in ranked), "입력값이 후보에 새었다"
    clicked = web_candidates.rank_candidates(_SCANNED, "button:has-text('Next')", "click")
    assert clicked[0]["ref"] == 4 and clicked[0]["disabled"] is True, clicked


def test_candidates_are_capped():
    many = [{"ref": i, "role": "button", "tag": "button", "label": f"b{i}"} for i in range(1, 40)]
    assert len(web_candidates.rank_candidates(many, None, "click")) == web_candidates.MAXIMUM_CANDIDATES


def test_selector_not_found_keeps_its_code_and_gains_candidates():
    page = _FakePage(None, _SCANNED)
    _el, _info, failure = web_element.locate_target(page, _args(selector="input[type=email]"), {}, "type",
                                                    should_wait=True)
    assert failure["code"] == "selector_not_found", failure
    assert failure["candidates"][0]["ref"] == 3
    assert failure["next"].startswith("web type --ref 3 --text"), failure["next"]
    assert "iframe_count" not in failure


def test_next_skips_a_disabled_top_candidate():
    page = _FakePage(None, _SCANNED)
    failure = web_element.locate_target(page, _args(selector="button:has-text('Next')"), {}, "click")[2]
    assert failure["candidates"][0]["ref"] == 4 and failure["candidates"][0]["disabled"] is True
    assert failure["next"].startswith("web click --ref 5"), failure["next"]


def test_ref_stale_gains_candidates_and_iframe_count():
    page = _FakePage(None, _SCANNED, frame_count=3)
    failure = web_element.locate_target(page, _args(ref=9, selector=None), {}, "click")[2]
    assert failure["code"] == "ref_stale" and failure["candidates"], failure
    assert failure["iframe_count"] == 2 and "iframe" in failure["hint"]


def test_scan_failure_leaves_the_original_failure():
    class Navigating(_FakePage):
        def evaluate(self, js, options):
            raise RuntimeError("Execution context was destroyed")
    failure = web_element.locate_target(Navigating(None), _args(), {}, "click")[2]
    assert failure["code"] == "selector_not_found" and "candidates" not in failure
    assert failure["next"] == "web find --text <글자>"


class TimeoutError(Exception):   # noqa: A001 — Playwright 예외 이름을 흉내 낸다
    pass


def test_timeout_while_acting_becomes_not_actionable_with_candidates():
    page = _FakePage(None, _SCANNED)
    args = _args(selector="#hidden", text="s3cret", text_env="PW", cred=None, timeout=None)

    def fill():
        raise TimeoutError('Locator.fill: Timeout 4000ms exceeded. value "s3cret"\nCall log:\n  - fill("s3cret")')
    failure = web_element.perform_on_target(page, args, "type", {"tag": "input", "visible": False}, fill)
    assert failure["code"] == "element_not_actionable" and failure["candidates"], failure
    assert "s3cret" not in str(failure), "비밀값이 결과에 새었다"
    assert "4초" in failure["error"]


def test_other_errors_are_not_swallowed():
    def boom():
        raise ValueError("Not a checkbox or radio button")
    with pytest.raises(ValueError):
        web_element.perform_on_target(_FakePage(None), _args(), "check", {}, boom)
    assert web_element.perform_on_target(_FakePage(None), _args(), "check", {}, lambda: None) is None


TARGET_ACTIONS = ("click", "type", "check", "select", "hover", "press", "download")


@pytest.mark.parametrize("action", TARGET_ACTIONS)
def test_target_actions_wait_briefly_unless_told(action):
    from pro_launch.cli import build_parser
    args = build_parser().parse_args(["web", action, "--root", "."])
    assert args.timeout is None
    assert web_element.target_wait_seconds(args) == 4 and web_element.outcome_wait_seconds(args) == 10
    raised = build_parser().parse_args(["web", action, "--timeout", "15", "--root", "."])
    assert web_element.target_wait_seconds(raised) == 15 and web_element.outcome_wait_seconds(raised) == 15


@pytest.mark.parametrize("action", ("open", "goto", "text", "assert", "find", "inspect"))
def test_other_actions_keep_the_full_wait(action):
    from pro_launch.cli import build_parser
    assert build_parser().parse_args(["web", action, "--root", "."]).timeout == 10


def test_shared_option_defaults_first_declaration_wins():
    shared = {"long": lambda p: p.add_argument("--timeout", type=int, default=10),
              "short": lambda p: p.add_argument("--timeout", type=int, default=None)}
    assert registry.shared_option_defaults(shared)["timeout"] == 10


# ── dialog (#892) — 상태 파일에 걸고, 붙을 때마다 다시 건다 ───────────────

def test_dialog_plan_is_written_to_state(tmp_path, capsys):
    state_f = tmp_path / "browser.json"
    state: dict = {}
    web_dialog.execute(argparse.Namespace(clear=False, accept=True, dismiss=False, text="새 이름"), state, state_f)
    assert rt_browser.read_state(state_f)["dialog"] == {"action": "accept", "text": "새 이름"}
    web_dialog.execute(argparse.Namespace(clear=True, accept=False, dismiss=False, text=None), state, state_f)
    assert "dialog" not in rt_browser.read_state(state_f)


class _FakeDialog:
    type, message = "prompt", "이름?"

    def __init__(self):
        self.calls = []

    def accept(self, *a):
        self.calls.append(("accept", a))

    def dismiss(self):
        self.calls.append(("dismiss", ()))


def test_dialog_handler_uses_the_plan_once_then_dismisses():
    state = {"dialog": {"action": "accept", "text": "새 이름"}}
    handler = web_session.dialog_handler(state)
    first, second = _FakeDialog(), _FakeDialog()
    handler(first)
    assert first.calls == [("accept", ("새 이름",))] and "dialog" not in state
    assert state[web_session.DIALOG_EVENT_KEY]["handled"] == "accept"
    handler(second)
    assert second.calls == [("dismiss", ())] and state[web_session.DIALOG_EVENT_KEY]["armed"] is False


def test_web_connect_rearms_the_dialog_handler():
    hooked = []

    class Page:
        def on(self, event, fn):
            hooked.append(event)
    assert web_session.arm_dialog(Page(), {}) and hooked == ["dialog"]


# ── 진짜 브라우저 ─────────────────────────────────────────────────────────

_FORM = """<!doctype html><meta charset="utf-8"><title>폼</title>
<form onsubmit="event.preventDefault(); document.title='보냄:' + document.getElementById('email').value">
<label for="email">이메일 주소</label><input id="email" name="email" value="a@b.c">
<label>비밀번호 <input type="password" name="pw" value="secret"></label>
<label><input type="checkbox" id="agree" name="agree"> 약관 동의</label>
<select id="city" name="city"><option value="seoul">서울</option><option value="busan">부산</option></select>
<button id="next" type="button" disabled>다음</button><button id="go" type="submit">확인</button>
<button id="ask" type="button" onclick="document.getElementById('answer').textContent='답:' + prompt('이름?')">묻기</button>
<span id="tip" title="t" onmouseover="document.getElementById('tipbox').hidden=false">도움말</span>
<p id="tipbox" hidden>TIP_MARK</p>
<a id="dl" href="/file.csv" download>내려받기</a>
</form><p id="answer"></p>
<p>line one</p><p>Target ALPHA here</p><p>after alpha</p><p>far away</p><p>alpha again</p>
""".encode()


@contextlib.contextmanager
def _session(tmp_path):
    ok, _ = rt_browser.require_playwright()
    if ok is None:
        pytest.skip("Playwright 없음 — web setup 후 실행된다")

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            is_file = self.path.startswith("/file.csv")
            body = b"a,b\n1,2\n" if is_file else _FORM
            self.send_response(200)
            self.send_header("Content-Type", "text/csv" if is_file else "text/html; charset=utf-8")
            if is_file:
                self.send_header("Content-Disposition", 'attachment; filename="file.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    proj = _repo(tmp_path, f"actions-{os.getpid()}", remote=None)
    state = common_state.state_dir("launch", proj)
    try:
        yield str(proj), f"http://127.0.0.1:{srv.server_port}/"
    finally:
        close_browser_for_test(run_cli, proj, state)
        srv.shutdown()
        shutil.rmtree(state, ignore_errors=True)


def web(r, *a, env_extra=None):
    return _j(run_cli("web", *a, "--root", r, env_extra=env_extra)[1])


@pytest.mark.local_only
def test_inspect_reads_the_form_and_its_refs_drive_actions(tmp_path):
    with _session(tmp_path) as (r, url):
        assert web(r, "open", "--url", url)["ok"]
        d = web(r, "inspect")
        by_name = {i.get("name") or i["label"]: i for i in d["items"]}
        assert by_name["email"]["label"] == "이메일 주소" and by_name["email"]["value"] == "a@b.c", d
        assert "value" not in by_name["pw"] and by_name["pw"]["has_value"] is True, "비밀번호 값이 새었다"
        assert by_name["agree"]["checked"] is False
        assert [o["value"] for o in by_name["city"]["options"]] == ["seoul", "busan"]
        assert by_name["다음"]["disabled"] is True
        near = web(r, "inspect", "--role", "input", "--near", "이메일")
        assert near["items"][0]["name"] == "email", near
        typed = web(r, "type", "--ref", str(near["items"][0]["ref"]), "--text", "x@y.z")
        assert typed["ok"], typed
        assert web(r, "inspect", "--role", "input", "--limit", "1")["truncated"] is True
        assert web(r, "inspect", "--near", "없는글자")["code"] == "near_not_found"


@pytest.mark.local_only
def test_disabled_button_is_reported_without_waiting(tmp_path):
    with _session(tmp_path) as (r, url):
        web(r, "open", "--url", url)
        import time
        started = time.monotonic()
        d = web(r, "click", "--selector", "#next", "--timeout", "8")
        assert d["code"] == "element_disabled", d
        assert time.monotonic() - started < 6, "타임아웃까지 기다렸다"


@pytest.mark.local_only
def test_select_check_press_hover_text_grep(tmp_path):
    with _session(tmp_path) as (r, url):
        web(r, "open", "--url", url)
        s = web(r, "select", "--selector", "#city", "--value", "부산")
        assert s["ok"] and s["selected"]["value"] == "busan", s
        assert web(r, "select", "--selector", "#city", "--value", "대구")["code"] == "option_not_found"
        assert web(r, "select", "--selector", "#email", "--value", "x")["code"] == "not_a_select"
        c = web(r, "check", "--selector", "#agree")
        assert c["ok"] and c["checked"] is True and c["checked_before"] is False, c
        assert web(r, "check", "--selector", "#agree", "--off")["checked"] is False
        h = web(r, "hover", "--selector", "#tip")
        assert h["ok"] and web(r, "text", "--grep", "TIP_MARK")["match_count"] == 1
        p = web(r, "press", "--selector", "#email", "--key", "Enter")
        assert p["ok"] and p["title"].startswith("보냄:"), p
        g = web(r, "text", "--grep", "alpha", "--around", "0")
        assert g["match_count"] == 3 and "far away" not in g["text"], g
        assert web(r, "press", "--key", "NoSuchKey")["code"] == "bad_key"


@pytest.mark.local_only
def test_dialog_is_armed_across_calls_and_reported(tmp_path):
    with _session(tmp_path) as (r, url):
        web(r, "open", "--url", url)
        assert web(r, "dialog", "--accept", "--text", "철수")["armed"]["action"] == "accept"
        c = web(r, "click", "--selector", "#ask")
        assert c["dialog"]["handled"] == "accept" and c["dialog"]["type"] == "prompt", c
        assert "답:철수" in web(r, "text", "--grep", "답:", "--around", "0")["text"]
        again = web(r, "click", "--selector", "#ask")
        assert again["dialog"]["handled"] == "dismiss", "한 번만 써야 한다"


@pytest.mark.local_only
def test_download_saves_into_the_run_folder(tmp_path):
    with _session(tmp_path) as (r, url):
        web(r, "open", "--url", url)
        run_dir = tmp_path / "run"
        d = web(r, "download", "--selector", "#dl", env_extra={"SHOT_DIR": str(run_dir)})
        assert d["ok"] and Path(d["file"]).parent == run_dir and d["bytes"] == 8, d


@pytest.mark.local_only
def test_guessed_selector_returns_candidates_quickly(tmp_path):
    import time
    with _session(tmp_path) as (r, url):
        web(r, "open", "--url", url)
        started = time.monotonic()
        missing = web(r, "type", "--selector", "input[type=email]", "--text", "x@y.z")
        assert missing["code"] == "selector_not_found", missing
        assert time.monotonic() - started < 8, "기본 대기가 짧아지지 않았다"
        assert missing["candidates"][0]["name"] == "email", missing["candidates"]
        typed = web(r, "type", "--ref", str(missing["candidates"][0]["ref"]), "--text", "x@y.z")
        assert typed["ok"], typed
        hidden = web(r, "click", "--selector", "#tipbox")
        assert hidden["code"] == "element_not_actionable" and hidden["candidates"], hidden
        assert hidden["next"].startswith("web click --ref"), hidden


# ── web wait: 선택자 문법 오류는 '안 보임' 이 아니다 ─────────────────────

def test_wait_reports_bad_selector_instead_of_waiting_until_timeout(monkeypatch):
    from types import SimpleNamespace

    from pro_launch.commands.web.actions import wait as web_wait

    class SyntaxBrokenScope:
        def locator(self, selector):
            raise RuntimeError(f'Locator.count: Unexpected token "" while parsing css selector "{selector}".')

    page = SimpleNamespace(url="https://example.test/", wait_for_timeout=lambda ms: None)
    monkeypatch.setattr(web_wait, "frame_scope", lambda page, args, action: (SyntaxBrokenScope(), None))
    args = SimpleNamespace(url_contains=None, text=None, gone=None, selector="div[", timeout=60)
    result = web_wait.execute(page, args, {})
    assert result["ok"] is False and result["code"] == "bad_selector"
