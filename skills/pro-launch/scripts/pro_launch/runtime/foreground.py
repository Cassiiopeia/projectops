"""Front app check: Android focused window · resumed activity, iOS app process liveness (#923).

The exit code of `monkey` · `simctl launch` only means "the launch was sent". Even if another session's sign-in screen covers it
or the app dies right away, it is 0 (observed). Here we check that it is actually in front after launch.
"""
from __future__ import annotations

import re
import subprocess
import time

from common.proc import sdk_tool

# Device-side command read in one go — focused window + resumed activity (grep runs on the device)
ANDROID_FOREGROUND_COMMAND = ("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'; "
                              "dumpsys activity activities | grep -E 'ResumedActivity'")
# Max wait for one dumpsys (s). A struggling device times out the window dump at 10 s (observed)
FOREGROUND_READ_TIMEOUT_SECONDS = 15
# Limit · interval for waiting until it comes to front after launch (s)
FOREGROUND_WAIT_SECONDS = 5.0
FOREGROUND_POLL_SECONDS = 0.5
# iOS: wait after simctl launch before checking the app is alive (s) — apps that crash at startup die within this
IOS_SETTLE_SECONDS = 2.5
IOS_LIST_TIMEOUT_SECONDS = 15

_FOCUS_PATTERN = re.compile(r"mCurrentFocus=(?:Window\{\S+ (?:u\d+ )?(?P<window>[^}]*)\}|(?P<null>null))")
_RESUMED_PATTERN = re.compile(r"(?:topResumedActivity|mResumedActivity|ResumedActivity)\s*[=:]\s*"
                              r"ActivityRecord\{\S+ (?:u\d+ )?(?P<package>[\w.]+)/(?P<activity>[\w.$]+)")
_NOT_RESPONDING_MARKER = "Not Responding:"


def parse_android_foreground(text: str) -> dict:
    """dumpsys output > {is_readable, package, activity, window, is_not_responding, resumed_package}.

    package: app of the focused window (or of the resumed activity if none). window: focused window name as is (to show what covers it).
    """
    focus = _FOCUS_PATTERN.search(text or "")
    resumed = _RESUMED_PATTERN.search(text or "")
    # If the window dump timed out ("DUMP TIMEOUT") there is no focus line — judge from the resumed activity if that was read
    result = {"is_readable": bool(focus or resumed),
              "package": None, "activity": None, "window": None, "is_not_responding": False,
              "resumed_package": resumed.group("package") if resumed else None}
    if focus and focus.group("window"):
        window = focus.group("window").strip()
        result["window"] = window
        if _NOT_RESPONDING_MARKER in window:
            # Not-responding dialog: "Application Not Responding: com.acme"
            result["is_not_responding"] = True
            result["package"] = window.split(_NOT_RESPONDING_MARKER, 1)[1].strip() or None
        elif "/" in window:
            package, activity = window.split("/", 1)
            result["package"], result["activity"] = package.strip(), activity.strip()
    if result["package"] is None and resumed and not result["window"]:
        # If the focused window is null, judge by the resumed activity (switching · right after cold boot)
        result["package"], result["activity"] = resumed.group("package"), resumed.group("activity")
    return result


def read_android_foreground(serial: str) -> dict:
    """Read once from the device. is_readable=false if adb is missing or times out."""
    adb = sdk_tool("adb")
    unreadable = parse_android_foreground("")
    if not adb:
        return unreadable
    try:
        r = subprocess.run([adb, "-s", serial, "shell", ANDROID_FOREGROUND_COMMAND], capture_output=True,
                           text=True, errors="replace", timeout=FOREGROUND_READ_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return unreadable
    return parse_android_foreground(((r.stdout or "") + (r.stderr or "")).replace("\r", ""))


def foreground_package(serial: str) -> str | None:
    """Android front app package. None if unreadable — attached to shot · tree results."""
    return read_android_foreground(serial)["package"]


def blocking_activity_of(foreground: dict) -> str | None:
    """One line for what covers it: "package/activity" · window name · null."""
    if foreground.get("activity"):
        return f"{foreground['package']}/{foreground['activity']}"
    return foreground.get("window")


def wait_for_android_foreground(serial: str, package: str, wait_seconds: float | None = None) -> dict:
    """Watch briefly until the target app comes to front > {state, foreground, waited_seconds}.

    state: match (in front) · other (something else in front) · not_responding (target app not-responding dialog) · unknown (unreadable).
    No waiting when unreadable — the device is struggling and repeating makes it slower.
    """
    started = time.monotonic()
    deadline = started + (FOREGROUND_WAIT_SECONDS if wait_seconds is None else wait_seconds)
    while True:
        foreground = read_android_foreground(serial)
        if not foreground["is_readable"]:
            state = "unknown"
            break
        is_target = package in (foreground["package"], foreground["resumed_package"])
        if is_target and not foreground["is_not_responding"]:
            state = "match"
            break
        state = "not_responding" if foreground["is_not_responding"] and foreground["package"] == package else "other"
        if time.monotonic() >= deadline:
            break
        time.sleep(FOREGROUND_POLL_SECONDS)
    return {"state": state, "foreground": foreground, "waited_seconds": round(time.monotonic() - started, 1)}


def ios_app_is_running(udid: str, bundle_id: str) -> bool | None:
    """Is the app (UIKitApplication:<bundle>) in the simulator's launchctl list. None if the list cannot be read."""
    try:
        r = subprocess.run(["xcrun", "simctl", "spawn", udid, "launchctl", "list"], capture_output=True,
                           text=True, errors="replace", timeout=IOS_LIST_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    listing = r.stdout or ""
    if r.returncode != 0 or not listing.strip():
        return None
    return f"UIKitApplication:{bundle_id}[" in listing
