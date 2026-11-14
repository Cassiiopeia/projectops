"""macOS mouse · keys · capture (#985) — CGEvent and mss. All coordinates are points (same space as AX).

Input is the fallback path used only when accessibility actions (AXPress·AXValue) do not work.
"""
from __future__ import annotations

import time

# Characters per key event — 1. Putting several characters in one event breaks one-char-per-box inputs (OTP) (observed)
TYPE_CHUNK_CHARS = 1
# Interval between events (s) — too fast and apps merge press and release
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
    # A double click sends click state rising 1 > 2 at the same spot
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
        # Length in UTF-16 units — emoji and supplementary-plane characters take 2
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
    """(x1, y1, x2, y2) point region > PNG bytes. None means the main screen. None without Screen Recording permission."""
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
    except Exception:   # noqa: BLE001 — no permission · region off screen — continue without capture (screen_changed: null)
        return None
