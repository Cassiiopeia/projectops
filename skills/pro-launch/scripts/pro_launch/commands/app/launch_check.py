"""app launch · relaunch 가 띄운 뒤 앞에 있는지 확인한 결과를 응답으로 만든다 (#923).

Android: 초점 창 · 재개된 액티비티가 대상 앱인가 (최대 ~5초 기다림).
iOS: 잠시 뒤 앱 프로세스가 살아 있나. 죽었으면 가장 새 크래시 리포트의 예외 줄.
판정 못 하면(unknown) 성공을 뒤집지 않는다 — 기기가 버거울 때 확인 자체가 막힌다.
"""
from __future__ import annotations

import time

from pro_launch.runtime import crash_reports, foreground
from pro_launch.runtime.output import out

# iOS 크래시 리포트가 디스크에 쓰이기를 더 기다리는 횟수 · 간격 (초)
CRASH_REPORT_WAIT_ATTEMPTS = 3
CRASH_REPORT_WAIT_SECONDS = 1.0


def check_after_launch(platform: str, dev_id: str, package: str, launched_epoch: float) -> dict:
    """> {state: ok|not_foreground|app_exited|unknown, ...}. launched_epoch: 띄우기 직전 time.time()."""
    if platform == "android":
        return _check_android(dev_id, package)
    return _check_ios(dev_id, package, launched_epoch)


def _check_android(serial: str, package: str) -> dict:
    waited = foreground.wait_for_android_foreground(serial, package)
    current = waited["foreground"]
    result = {"foreground_package": current["package"] or current["resumed_package"],
              "foreground_waited_seconds": waited["waited_seconds"]}
    if waited["state"] == "match":
        return {"state": "ok", **result}
    if waited["state"] == "unknown":
        return {"state": "unknown", **result}
    return {"state": "not_foreground", **result, "blocking_activity": foreground.blocking_activity_of(current),
            "is_not_responding": waited["state"] == "not_responding"}


def _check_ios(udid: str, bundle_id: str, launched_epoch: float) -> dict:
    time.sleep(foreground.IOS_SETTLE_SECONDS)
    is_running = foreground.ios_app_is_running(udid, bundle_id)
    if is_running is None:
        return {"state": "unknown"}
    if is_running:
        return {"state": "ok", "is_app_running": True}
    # 죽었다 — 리포트는 죽은 뒤 조금 늦게 쓰인다
    report = None
    for attempt in range(CRASH_REPORT_WAIT_ATTEMPTS):
        report = crash_reports.newest_crash_report(bundle_id, udid, launched_epoch)
        if report or attempt == CRASH_REPORT_WAIT_ATTEMPTS - 1:
            break
        time.sleep(CRASH_REPORT_WAIT_SECONDS)
    return {"state": "app_exited", "is_app_running": False, "crash_report": report}


def launch_failure_response(action: str, platform: str, dev_id: str, package: str, check: dict,
                            **extra) -> int:
    """not_foreground · app_exited 실패 응답. 기존 code 는 건드리지 않는다."""
    if check["state"] == "not_foreground":
        blocker = check.get("blocking_activity") or "(초점 창 없음)"
        return out({"ok": False, "code": "not_foreground", "action": action, "platform": platform,
                    "device": dev_id, "package": package, "foreground_package": check.get("foreground_package"),
                    "blocking_activity": check.get("blocking_activity"),
                    "is_not_responding": check.get("is_not_responding", False),
                    "error": f"{package} 가 앞으로 나오지 않았다 — 맨 위: {blocker}",
                    "summary": f"{package} {action} 했지만 다른 화면이 앞에 있다",
                    "next": "app shot 으로 가리는 화면을 본다. 다른 세션 소유(device_owned_by_other)면 사용자에게 묻고, "
                            "아니면 app relaunch 를 다시 하거나 device reboot",
                    **extra})
    report = check.get("crash_report")
    return out({"ok": False, "code": "app_exited", "action": action, "platform": platform, "device": dev_id,
                "package": package, "crash_report": report,
                "error": f"{package} 가 띄운 직후 종료됐다" + (f" — {report['exception_line']}" if report
                                                                   and report.get("exception_line") else ""),
                "summary": f"{package} {action} 직후 종료",
                "next": (f"크래시 리포트를 읽는다: {report['path']}" if report else
                         "리포트가 없다 — xcrun simctl launch --console-pty 로 시작 로그를 본다"),
                **extra})
