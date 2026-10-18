"""맨 앞 앱 확인: Android 초점 창 · 재개된 액티비티, iOS 앱 프로세스 생존 (#923).

`monkey` · `simctl launch` 의 종료코드는 "띄우라고 보냈다"일 뿐이다. 다른 세션의 로그인 화면이 위를 덮고 있거나
앱이 곧바로 죽어도 0 이 나온다(실측). 띄운 뒤 실제로 앞에 있는지 여기서 본다.
"""
from __future__ import annotations

import re
import subprocess
import time

from common.proc import sdk_tool

# 한 번에 읽는 기기 쪽 명령 — 초점 창 + 재개된 액티비티 (grep 은 기기 안에서)
ANDROID_FOREGROUND_COMMAND = ("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'; "
                              "dumpsys activity activities | grep -E 'ResumedActivity'")
# dumpsys 한 번의 최대 대기 (초). 기기가 버거우면 window 덤프가 10초 시간 초과를 낸다(실측)
FOREGROUND_READ_TIMEOUT_SECONDS = 15
# 띄운 뒤 앞으로 나오기를 기다리는 한도 · 간격 (초)
FOREGROUND_WAIT_SECONDS = 5.0
FOREGROUND_POLL_SECONDS = 0.5
# iOS: simctl launch 뒤 앱이 살아 있는지 보기 전 기다림 (초) — 시작 직후 죽는 앱은 이 안에 죽는다
IOS_SETTLE_SECONDS = 2.5
IOS_LIST_TIMEOUT_SECONDS = 15

_FOCUS_PATTERN = re.compile(r"mCurrentFocus=(?:Window\{\S+ (?:u\d+ )?(?P<window>[^}]*)\}|(?P<null>null))")
_RESUMED_PATTERN = re.compile(r"(?:topResumedActivity|mResumedActivity|ResumedActivity)\s*[=:]\s*"
                              r"ActivityRecord\{\S+ (?:u\d+ )?(?P<package>[\w.]+)/(?P<activity>[\w.$]+)")
_NOT_RESPONDING_MARKER = "Not Responding:"


def parse_android_foreground(text: str) -> dict:
    """dumpsys 출력 > {is_readable, package, activity, window, is_not_responding, resumed_package}.

    package: 초점 창의 앱 (없으면 재개된 액티비티의 앱). window: 초점 창 이름 그대로 (가리는 것을 보여 줄 때).
    """
    focus = _FOCUS_PATTERN.search(text or "")
    resumed = _RESUMED_PATTERN.search(text or "")
    # window 덤프가 시간 초과("DUMP TIMEOUT")면 초점 줄이 없다 — 재개된 액티비티라도 읽혔으면 판정한다
    result = {"is_readable": bool(focus or resumed),
              "package": None, "activity": None, "window": None, "is_not_responding": False,
              "resumed_package": resumed.group("package") if resumed else None}
    if focus and focus.group("window"):
        window = focus.group("window").strip()
        result["window"] = window
        if _NOT_RESPONDING_MARKER in window:
            # 응답 없음 대화상자: "Application Not Responding: com.acme"
            result["is_not_responding"] = True
            result["package"] = window.split(_NOT_RESPONDING_MARKER, 1)[1].strip() or None
        elif "/" in window:
            package, activity = window.split("/", 1)
            result["package"], result["activity"] = package.strip(), activity.strip()
    if result["package"] is None and resumed and not result["window"]:
        # 초점 창이 null 이면 재개된 액티비티로 판정 (전환 중·콜드 부팅 직후)
        result["package"], result["activity"] = resumed.group("package"), resumed.group("activity")
    return result


def read_android_foreground(serial: str) -> dict:
    """기기에서 한 번 읽는다. adb 가 없거나 시간 초과면 is_readable=false."""
    adb = sdk_tool("adb")
    unreadable = parse_android_foreground("")
    if not adb:
        return unreadable
    try:
        r = subprocess.run([adb, "-s", serial, "shell", ANDROID_FOREGROUND_COMMAND], capture_output=True,
                           text=True, timeout=FOREGROUND_READ_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return unreadable
    return parse_android_foreground(((r.stdout or "") + (r.stderr or "")).replace("\r", ""))


def foreground_package(serial: str) -> str | None:
    """Android 맨 앞 앱 패키지. 못 읽으면 None — shot · tree 결과에 싣는 용도."""
    return read_android_foreground(serial)["package"]


def blocking_activity_of(foreground: dict) -> str | None:
    """가리고 있는 것 한 줄: "패키지/액티비티" · 창 이름 · null."""
    if foreground.get("activity"):
        return f"{foreground['package']}/{foreground['activity']}"
    return foreground.get("window")


def wait_for_android_foreground(serial: str, package: str, wait_seconds: float | None = None) -> dict:
    """대상 앱이 앞으로 나올 때까지 짧게 본다 > {state, foreground, waited_seconds}.

    state: match (앞에 있음) · other (다른 것이 앞) · not_responding (대상 앱 응답 없음 대화상자) · unknown (못 읽음).
    못 읽으면 기다리지 않는다 — 기기가 버거운 상태라 반복하면 더 느려진다.
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
    """시뮬레이터 안 launchctl 목록에 앱(UIKitApplication:<번들>)이 있나. 목록을 못 읽으면 None."""
    try:
        r = subprocess.run(["xcrun", "simctl", "spawn", udid, "launchctl", "list"], capture_output=True,
                           text=True, timeout=IOS_LIST_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    listing = r.stdout or ""
    if r.returncode != 0 or not listing.strip():
        return None
    return f"UIKitApplication:{bundle_id}[" in listing
