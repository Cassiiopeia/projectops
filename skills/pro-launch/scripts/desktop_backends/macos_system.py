"""macOS 창 목록 · 화면 · 준비 상태 (#985). Quartz · AppKit 은 함수 안에서만 가져온다."""
from __future__ import annotations

import ctypes
import ctypes.util

from desktop_backends import macos_nodes

# 창 목록에서 빼는 소유자 — Dock · 바탕화면 · 메뉴바 · 창 관리자 그림자
EXCLUDED_OWNERS = {"Dock", "Window Server", "WindowManager", "Control Center", "SystemUIServer",
                   "Wallpaper"}
# 알림 센터: 창이 없어도 AXFrontmost 가 항상 True 라 앞 앱 후보에서 뺀다
NOTIFICATION_CENTER_BUNDLE_ID = "com.apple.notificationcenterui"
# NSApplicationActivationPolicyRegular — Dock 에 뜨는 일반 앱. 그 외(에이전트·백그라운드)의 창은 overlay 후보다
ACTIVATION_POLICY_REGULAR = 0
# NSApplicationActivateIgnoringOtherApps
ACTIVATE_IGNORING_OTHER_APPS = 1 << 1
# 앞으로 가져온 뒤 확인까지 기다리는 초
ACTIVATE_SETTLE_SECONDS = 0.15


def cg_windows() -> list[dict]:
    """화면 위 창 (앞에서 뒤 순서). frame 은 point (x, y, w, h)."""
    from Quartz import (CGWindowListCopyWindowInfo, kCGNullWindowID, kCGWindowListExcludeDesktopElements,
                        kCGWindowListOptionOnScreenOnly)
    infos = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                                       kCGNullWindowID) or []
    rows = []
    for info in infos:
        bounds = info.get("kCGWindowBounds") or {}
        frame = (float(bounds.get("X", 0)), float(bounds.get("Y", 0)),
                 float(bounds.get("Width", 0)), float(bounds.get("Height", 0)))
        rows.append({"number": int(info.get("kCGWindowNumber", 0)), "pid": int(info.get("kCGWindowOwnerPID", 0)),
                     "owner": info.get("kCGWindowOwnerName") or "", "title": info.get("kCGWindowName") or "",
                     "layer": int(info.get("kCGWindowLayer", 0)), "alpha": float(info.get("kCGWindowAlpha", 1.0)),
                     "frame": frame})
    return rows


def screens() -> list[macos_nodes.Screen]:
    """화면 목록 — 첫 항목이 주 화면(메뉴바 있는 화면)."""
    from AppKit import NSScreen
    all_screens = list(NSScreen.screens() or [])
    if not all_screens:
        return [((0, 0, 0, 0), 1.0)]
    main_height = all_screens[0].frame().size.height
    result = []
    for screen in all_screens:
        f = screen.frame()
        rect = macos_nodes.flip_ns_frame((f.origin.x, f.origin.y, f.size.width, f.size.height), main_height)
        result.append((rect, float(screen.backingScaleFactor())))
    return result


def app_info(pid: int) -> tuple[str, str, bool]:
    """(앱 이름, 번들 id, 일반 앱인가)."""
    from AppKit import NSRunningApplication
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app is None:
        return "", "", False
    return (app.localizedName() or "", app.bundleIdentifier() or "",
            int(app.activationPolicy()) == ACTIVATION_POLICY_REGULAR)


def frontmost_pid() -> int | None:
    """앞에 있는 앱 pid — AX 시스템 요소 > 실패 시 앱별 AXFrontmost.

    NSWorkspace.frontmostApplication 은 run loop 가 없는 CLI 에서 갱신되지 않아 옛 앱을 돌려준다 (실측).
    """
    from ApplicationServices import (AXUIElementCopyAttributeValue, AXUIElementCreateSystemWide,
                                     AXUIElementGetPid)
    err, app = AXUIElementCopyAttributeValue(AXUIElementCreateSystemWide(), "AXFocusedApplication", None)
    if err == 0 and app is not None:
        err, pid = AXUIElementGetPid(app, None)
        if err == 0:
            return int(pid)
    # macOS 27 은 시스템 요소 질의가 항상 -25204 (kAXErrorCannotComplete) — 앱별로 묻는다 (#1002)
    return _frontmost_pid_by_app_attribute()


def _frontmost_pid_by_app_attribute() -> int | None:
    """화면 위 창을 가진 앱 중 AXFrontmost 가 True 인 앱 (앞 창 순서).

    True 가 여럿이면 일반 앱 우선 > 알림 센터 제외한 에이전트 앱 (알림 센터는 항상 True, 실측)
    """
    from ApplicationServices import AXUIElementCopyAttributeValue, AXUIElementCreateApplication
    checked_pids: list[int] = []
    frontmost_pids: list[int] = []
    for row in cg_windows():
        pid = row["pid"]
        if pid in checked_pids or row["owner"] in EXCLUDED_OWNERS:
            continue
        checked_pids.append(pid)
        err, is_frontmost = AXUIElementCopyAttributeValue(AXUIElementCreateApplication(pid), "AXFrontmost", None)
        if err == 0 and is_frontmost:
            frontmost_pids.append(pid)
    agent_pid = None
    for pid in frontmost_pids:
        _, bundle_id, is_regular = app_info(pid)
        if is_regular:
            return pid
        if agent_pid is None and bundle_id != NOTIFICATION_CENTER_BUNDLE_ID:
            agent_pid = pid
    return agent_pid


def activate(pid: int, app_element) -> bool:
    """앱을 앞으로: AXFrontmost > activateWithOptions, 실제 앞 창 pid 로 판정
    (macOS 14+ 는 백그라운드의 activateWithOptions 를 무시하고도 True 반환 — 실측)"""
    import time

    from ApplicationServices import AXUIElementSetAttributeValue
    from AppKit import NSRunningApplication
    AXUIElementSetAttributeValue(app_element, "AXFrontmost", True)
    time.sleep(ACTIVATE_SETTLE_SECONDS)
    if frontmost_pid() == pid:
        return True
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app is not None:
        app.activateWithOptions_(ACTIVATE_IGNORING_OTHER_APPS)
        time.sleep(ACTIVATE_SETTLE_SECONDS)
    return frontmost_pid() == pid


def is_secure_input_on() -> bool:
    """비밀번호 칸 등이 Secure Event Input 을 켰는가 — 진단용 (그 앱에 보낸 합성 키는 들어간다, 실측)."""
    path = ctypes.util.find_library("Carbon")
    if not path:
        return False
    carbon = ctypes.cdll.LoadLibrary(path)
    carbon.IsSecureEventInputEnabled.restype = ctypes.c_bool
    return bool(carbon.IsSecureEventInputEnabled())


def readiness(rows: list[dict] | None = None) -> dict:
    from ApplicationServices import AXIsProcessTrusted
    from Quartz import CGPreflightScreenCaptureAccess, CGSessionCopyCurrentDictionary
    rows = cg_windows() if rows is None else rows
    session = CGSessionCopyCurrentDictionary()
    owners = [r["owner"] for r in rows if r["frame"][2] > 0 and r["frame"][3] > 0]
    ready = macos_nodes.readiness_from(dict(session) if session else {}, owners, bool(AXIsProcessTrusted()),
                                       bool(CGPreflightScreenCaptureAccess()))
    ready["secure_input"] = is_secure_input_on()
    return ready
