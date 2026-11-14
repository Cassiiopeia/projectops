"""macOS window list · screens · readiness (#985). Quartz · AppKit are imported only inside functions."""
from __future__ import annotations

import ctypes
import ctypes.util
import subprocess

from desktop_backends import macos_nodes

# Owners excluded from the window list — Dock · desktop · menu bar · window manager shadows
EXCLUDED_OWNERS = {"Dock", "Window Server", "WindowManager", "Control Center", "SystemUIServer",
                   "Wallpaper"}
# Notification Center: AXFrontmost is always True even without windows, so it is excluded from front-app candidates
NOTIFICATION_CENTER_BUNDLE_ID = "com.apple.notificationcenterui"
# NSApplicationActivationPolicyRegular — regular apps shown in the Dock. Windows of others (agent·background) are overlay candidates
ACTIVATION_POLICY_REGULAR = 0
# NSApplicationActivateIgnoringOtherApps
ACTIVATE_IGNORING_OTHER_APPS = 1 << 1
# Seconds to wait after bringing to front before confirming
ACTIVATE_SETTLE_SECONDS = 0.15
# CGEventSourceStateID: based on hardware (HID) input — less affected by other apps' synthetic events
EVENT_SOURCE_HID_SYSTEM_STATE = 1
# 2 CGEventTypes: keyDown 10, flagsChanged 12 (only Shift·Cmd pressed) — the mouse is checked separately by cursor comparison
KEYBOARD_EVENT_TYPES = (10, 12)
CORE_GRAPHICS_PATH = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"


def cg_windows() -> list[dict]:
    """On-screen windows (front to back). frame is in points (x, y, w, h)."""
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
    """Screen list — the first entry is the main screen (the one with the menu bar)."""
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
    """(app name, bundle id, is a regular app)."""
    from AppKit import NSRunningApplication
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app is None:
        return "", "", False
    return (app.localizedName() or "", app.bundleIdentifier() or "",
            int(app.activationPolicy()) == ACTIVATION_POLICY_REGULAR)


def frontmost_pid() -> int | None:
    """pid of the front app — AX system element > on failure, per-app AXFrontmost.

    NSWorkspace.frontmostApplication is not refreshed in a CLI without a run loop and returns an old app (observed).
    """
    from ApplicationServices import (AXUIElementCopyAttributeValue, AXUIElementCreateSystemWide,
                                     AXUIElementGetPid)
    err, app = AXUIElementCopyAttributeValue(AXUIElementCreateSystemWide(), "AXFocusedApplication", None)
    if err == 0 and app is not None:
        err, pid = AXUIElementGetPid(app, None)
        if err == 0:
            return int(pid)
    # On macOS 27 system element queries always return -25204 (kAXErrorCannotComplete) — ask per app (#1002)
    return _frontmost_pid_by_app_attribute()


def _frontmost_pid_by_app_attribute() -> int | None:
    """Among apps with on-screen windows, the one whose AXFrontmost is True (front window order).

    If several are True: regular apps first > agent apps excluding Notification Center (Notification Center is always True, observed)
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
    """Bring the app to front: AXFrontmost > activateWithOptions, judged by the actual front window pid
    (macOS 14+ ignores background activateWithOptions yet returns True — observed)"""
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
    """Did something like a password field turn on Secure Event Input — diagnostic (synthetic keys sent to that app still go in, observed)."""
    path = ctypes.util.find_library("Carbon")
    if not path:
        return False
    carbon = ctypes.cdll.LoadLibrary(path)
    carbon.IsSecureEventInputEnabled.restype = ctypes.c_bool
    return bool(carbon.IsSecureEventInputEnabled())


def seconds_since_key_input() -> float | None:
    """Seconds since the last keyboard input (CGEventSourceSecondsSinceLastEventType). No permission needed, None on failure (#985)."""
    try:
        cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics") or CORE_GRAPHICS_PATH)
        since = cg.CGEventSourceSecondsSinceLastEventType
        since.restype = ctypes.c_double
        since.argtypes = (ctypes.c_int32, ctypes.c_uint32)
        values = [float(since(EVENT_SOURCE_HID_SYSTEM_STATE, t)) for t in KEYBOARD_EVENT_TYPES]
    except (OSError, AttributeError):
        return None
    values = [v for v in values if v >= 0]
    return min(values) if values else None


def parent_by_pid() -> dict[int, int]:
    """pid → parent pid (ps). Empty dict on failure."""
    try:
        output = subprocess.run(["ps", "-ax", "-o", "pid=,ppid="], capture_output=True, text=True, errors="replace",
                                timeout=5, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    pairs = (line.split() for line in output.splitlines())
    return {int(p[0]): int(p[1]) for p in pairs if len(p) == 2 and p[0].isdigit() and p[1].isdigit()}


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
