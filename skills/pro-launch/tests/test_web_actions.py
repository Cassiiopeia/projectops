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
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_launch_cli import _j, _repo, run_cli  # noqa: E402
from pro_launch.commands.web import element as web_element  # noqa: E402


# ── 동작별 도움말 · 옵션 거절 (#896) ─────────────────────────────────────

def test_option_of_another_action_is_rejected_with_the_valid_list(tmp_path):
    rc, out, _ = run_cli("web", "type", "--root", str(_repo(tmp_path)), "--selector", "#x",
                         "--expect-url", "/home", home=tmp_path)
    d = _j(out)
    assert rc != 0 and d["code"] == "bad_args", d
    assert "--expect-url" in d["error"] and "--text-env" in d["error"], d


# 다른 스킬이 문서대로 부르는 조합 — 하나라도 bad_args 면 그 스킬이 깨진다
CALLER_COMBINATIONS = [
    ["open", "--url", "http://x", "--headed", "--readonly", "--ignore-cert-errors", "--timeout", "5"],
    ["click", "--ref", "1", "--expect-url", "/home", "--confirm-mutating", "--timeout", "2"],
    ["type", "--selector", "#v", "--text-env", "PW"],
]


@pytest.mark.parametrize("argv", CALLER_COMBINATIONS, ids=lambda a: " ".join(a[:2]))
def test_documented_caller_combinations_still_parse(argv):
    from pro_launch.cli import build_parser
    args = build_parser().parse_args(["web", *argv, "--root", "."])
    assert args.action == argv[0]
    # 선언하지 않은 공통 옵션도 기본값으로 속성은 있다 — 디스패처가 그대로 읽는다
    assert hasattr(args, "text_env") and hasattr(args, "ref")


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
