"""되돌리기 어려운 동작인지 문구로 가르는 규칙 — web 과 desktop 이 함께 쓴다 (#985).

web 은 읽기 전용 세션(`web open --readonly`)에서만 막고, desktop 은 기본으로 막는다.
판단은 글자만 보므로 어느 화면에서 왔는지와 무관하다.
"""
from __future__ import annotations

import re


# 막는 버튼 문구. "취소·확인"은 대화상자를 닫는 데도 쓰여 넣지 않았다.
MUTATING_RE = re.compile(
    r"(삭제|제거|출시|게시|제출|전송|보내기|저장|승인|결제|구매|업로드|배포|폐기|롤아웃|"
    r"\b(delete|remove|publish|release|roll ?out|submit|send|save|approve|pay|purchase|upload|deploy|discard)\b)",
    re.IGNORECASE)

# 데스크톱에서만 더 막는 문구 — 설치 마법사·약관 동의는 브라우저보다 데스크톱에서 흔하다.
# 허용·신뢰: Apple 계정 로그인 승인(2FA)·권한 팝업·인증서 신뢰 — 남의 로그인까지 승인할 수 있다.
# "다음·Next"는 넣지 않는다. 마법사를 넘기는 버튼이라 막으면 아무것도 못 한다.
DESKTOP_MUTATING_RE = re.compile(
    r"(설치|동의|마침|완료|포맷|초기화|허용|신뢰|"
    r"\b(install|agree|accept|finish|format|reset|uninstall|allow|trust)\b)",
    re.IGNORECASE)

# 화면 이동으로 보는 요소 — 문구에 "제출·게시"가 있어도 막지 않는다.
# Play Console 의 "제출 활동"·"게시 개요"는 기록을 보는 링크인데, 문구만 보면 위험 버튼으로 걸렸다(실측).
NAV_ROLES = {"link", "tab", "row", "menuitem", "treeitem", "option"}


def is_mutating_label(label: str, *, is_desktop: bool = False) -> bool:
    """버튼 문구가 되돌리기 어려운 동작인가. is_desktop=True 면 설치·동의 계열도 막는다."""
    text = label or ""
    if MUTATING_RE.search(text):
        return True
    return is_desktop and bool(DESKTOP_MUTATING_RE.search(text))
