"""web 세션의 탭 고르기 · 제목 읽기 (#860).

실측(Windows · 설치된 Chrome · 영속 프로필): 시작할 때 Chrome 이 chrome://privacy-sandbox-dialog 안내 탭을
함께 띄웠고, 마지막 탭을 그냥 쓰면 그 탭을 잡았다가 이동하는 순간 닫혀 `web open --url` 이 간헐적으로 실패했다.
탭 순서는 실행마다 달랐다. 또 리다이렉트 도중 `page.title()` 을 부르면 'Execution context was destroyed' 로 터졌다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.commands.web import session  # noqa: E402


class _Page:
    def __init__(self, url, closed=False, title_errors=0, title="제목"):
        self.url = url
        self._closed = closed
        self._errors = title_errors
        self._title = title

    def is_closed(self):
        return self._closed

    def wait_for_load_state(self, *a, **k):
        return None

    def title(self):
        if self._errors:
            self._errors -= 1
            raise RuntimeError("Page.title: Execution context was destroyed, most likely because of a navigation")
        return self._title


class _Ctx:
    def __init__(self, pages):
        self.pages = pages
        self.created = []

    def new_page(self):
        p = _Page("about:blank")
        self.created.append(p)
        self.pages.append(p)
        return p


DIALOG = "chrome://privacy-sandbox-dialog/notice"


@pytest.mark.parametrize("order", ["dialog_last", "dialog_first"])
def test_work_page_never_picks_chromes_own_notice_tab(order):
    blank, dialog = _Page("about:blank"), _Page(DIALOG)
    ctx = _Ctx([blank, dialog] if order == "dialog_last" else [dialog, blank])
    assert session.work_page(ctx) is blank
    assert ctx.created == []

