"""Rules that tell by text whether an action is hard to undo — shared by web and desktop (#985).

web blocks only in read-only sessions (`web open --readonly`); desktop blocks by default.
The decision looks only at text, so it does not matter which screen it came from.
"""
from __future__ import annotations

import re


# Button text to block. "Cancel·OK" are left out because they also close dialogs.
MUTATING_RE = re.compile(
    r"(삭제|제거|출시|게시|제출|전송|보내기|저장|승인|결제|구매|업로드|배포|폐기|롤아웃|"
    r"\b(delete|remove|publish|release|roll ?out|submit|send|save|approve|pay|purchase|upload|deploy|discard)\b)",
    re.IGNORECASE)

# Extra text blocked only on desktop — installer wizards·terms agreements are more common on desktop than in browsers.
# Allow·trust: Apple Account sign-in approval (2FA)·permission popups·certificate trust — could approve someone else's sign-in.
# "Next" is not included. It advances wizards, so blocking it would make nothing possible.
DESKTOP_MUTATING_RE = re.compile(
    r"(설치|동의|마침|완료|포맷|초기화|허용|신뢰|"
    r"\b(install|agree|accept|finish|format|reset|uninstall|allow|trust)\b)",
    re.IGNORECASE)

# Elements treated as navigation — not blocked even if the text has "submit·publish".
# Play Console's "제출 활동" (submission activity)·"게시 개요" (publishing overview) are links to view records, yet text alone flagged them as risky buttons (observed).
NAV_ROLES = {"link", "tab", "row", "menuitem", "treeitem", "option"}


def is_mutating_label(label: str, *, is_desktop: bool = False) -> bool:
    """Is the button text an action that is hard to undo. With is_desktop=True, install·agree types are blocked too."""
    text = label or ""
    if MUTATING_RE.search(text):
        return True
    return is_desktop and bool(DESKTOP_MUTATING_RE.search(text))
