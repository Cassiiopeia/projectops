"""macOS 마우스 · 키 · 캡처 (#985) — CGEvent 와 mss. 좌표는 전부 point (AX 와 같은 좌표계).

입력은 접근성 동작(AXPress·AXValue)이 안 될 때만 쓰는 대체 경로다.
"""
from __future__ import annotations

import time

# 키 이벤트 하나에 싣는 글자 수 — 1. 여러 글자를 한 이벤트에 실으면 한 칸 한 글자 입력칸(OTP)이 깨진다 (실측)
TYPE_CHUNK_CHARS = 1
# 이벤트 사이 간격 (초) — 너무 빠르면 앱이 눌림·뗌을 합친다
EVENT_GAP_SECONDS = 0.02


def _post(event) -> None:
    from Quartz import CGEventPost, kCGHIDEventTap
    CGEventPost(kCGHIDEventTap, event)
    time.sleep(EVENT_GAP_SECONDS)


def cursor_points() -> tuple[float, float]:
    from Quartz import CGEventCreate, CGEventGetLocation
    loc = CGEventGetLocation(CGEventCreate(None))
    return float(loc.x), float(loc.y)


def click_points(x: float, y: float, button: str = "left", is_double: bool = False) -> tuple[bool, str]:
    import Quartz as Q
    if button == "right":
        down, up, which = Q.kCGEventRightMouseDown, Q.kCGEventRightMouseUp, Q.kCGMouseButtonRight
    else:
        down, up, which = Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp, Q.kCGMouseButtonLeft
    point = (x, y)
    _post(Q.CGEventCreateMouseEvent(None, Q.kCGEventMouseMoved, point, which))
    # 더블클릭은 같은 자리에서 click state 를 1 > 2 로 올려 보낸다
    for state in ((1, 2) if is_double else (1,)):
        for kind in (down, up):
            event = Q.CGEventCreateMouseEvent(None, kind, point, which)
            Q.CGEventSetIntegerValueField(event, Q.kCGMouseEventClickState, state)
            _post(event)
    return True, f"clicked at {round(x)},{round(y)} (points)"


def type_unicode(text: str) -> tuple[bool, str]:
    import Quartz as Q
    for start in range(0, len(text), TYPE_CHUNK_CHARS):
        chunk = text[start:start + TYPE_CHUNK_CHARS]
        # 길이는 UTF-16 단위 — 이모지·보조 평면 글자는 2칸
        units = len(chunk.encode("utf-16-le")) // 2
        for is_down in (True, False):
            event = Q.CGEventCreateKeyboardEvent(None, 0, is_down)
            Q.CGEventKeyboardSetUnicodeString(event, units, chunk)
            _post(event)
    return True, f"typed {len(text)} characters"


def press_key(code: int, flags: int) -> tuple[bool, str]:
    import Quartz as Q
    for is_down in (True, False):
        event = Q.CGEventCreateKeyboardEvent(None, code, is_down)
        Q.CGEventSetFlags(event, flags)
        _post(event)
    return True, f"key {code}"


def grab_points(region: tuple[float, float, float, float] | None) -> bytes | None:
    """(x1, y1, x2, y2) point 영역 > PNG bytes. None 이면 주 화면. 화면 기록 권한이 없으면 None."""
    try:
        import mss
        import mss.tools
        with mss.mss() as capture:
            if region is None:
                monitor = capture.monitors[1]
            else:
                x1, y1, x2, y2 = region
                monitor = {"left": int(x1), "top": int(y1), "width": max(1, int(x2 - x1)),
                           "height": max(1, int(y2 - y1))}
            shot = capture.grab(monitor)
            return mss.tools.to_png(shot.rgb, shot.size)
    except Exception:   # noqa: BLE001 — 권한 없음 · 화면 밖 영역 — 캡처 없이 계속한다 (screen_changed: null)
        return None
