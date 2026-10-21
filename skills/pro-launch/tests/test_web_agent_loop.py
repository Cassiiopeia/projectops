"""agent 가 혼자 브라우저를 몰 수 있는가 (#825).

2026-10-10 Play Console 실측에서 겪은 것을 그대로 재현한다.
  · 링크가 아닌 셀을 눌렀는데 ok 가 나왔다           → click 이 무엇을 눌렀고 바뀌었는지 말해야 한다
  · 화면을 읽을 수 없어 선택자를 추측했다             → find / text
  · 추측한 클릭이 엉뚱한 메뉴로 튀었다                 → ref 로 정확히 누르고, 기대가 안 오면 실패
  · 관리 콘솔에서 되돌릴 수 없는 버튼을 누를 수 있었다 → --readonly
  · 떠 있던 브라우저가 있는데 open 이 실패했다        → reused
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_launch_cli import _repo  # noqa: E402
from pro_launch.commands.web import targets as web_targets  # noqa: E402
from pro_launch.runtime import browser as rt_browser  # noqa: E402


# ── 브라우저 없이 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("info", [
    {"tag": "button", "text": "검토를 위해 변경사항 전송"},
    {"tag": "div", "role": "button", "aria": "Publish"},
    {"tag": "input", "text": "Submit"},
])
def test_buttons_with_action_words_are_mutating(info):
    assert web_targets.is_mutating_target(info)


def test_doctor_reports_an_abandoned_browser(tmp_path):
    """3일 묵은 브라우저가 살아 있었는데 아무도 몰랐다 (Play Console 실측). 살아 있는 pid 로 흉내 낸다."""
    proj = _repo(tmp_path)
    st = rt_browser.state_path(proj)
    rt_browser.write_state(st, {"cdp": "http://127.0.0.1:1", "pid": os.getpid(),
                                     "opened_at": "2026-10-06 22:09:48", "last_used": "2026-10-06 22:10:00"})
    b = rt_browser.open_browser_status(st)
    assert b["alive"] and b["stale"] and "web close" in b["hint"], b
    rt_browser.write_state(st, {"pid": os.getpid(), "last_used": __import__("time").strftime("%Y-%m-%d %H:%M:%S")})
    assert rt_browser.open_browser_status(st)["stale"] is False

