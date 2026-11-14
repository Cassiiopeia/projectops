"""Turn the check that app launch/relaunch is in the foreground after launch into a response (#923).

Android: is the focused window / resumed activity the target app (waits up to ~5s).
iOS: is the app process alive shortly after. If it died, the exception line of the newest crash report.
If undecidable (unknown), success is not overturned — the check itself gets blocked when the device is struggling.
"""
from __future__ import annotations

import time

from pro_launch.runtime import crash_reports, foreground
from pro_launch.runtime.output import out

# Extra retries and interval (seconds) waiting for the iOS crash report to be written to disk
CRASH_REPORT_WAIT_ATTEMPTS = 3
CRASH_REPORT_WAIT_SECONDS = 1.0


def check_after_launch(platform: str, dev_id: str, package: str, launched_epoch: float) -> dict:
    """> {state: ok|not_foreground|app_exited|unknown, ...}. launched_epoch: time.time() just before launch."""
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
    # It died — the report is written a little after the crash
    report = None
    for attempt in range(CRASH_REPORT_WAIT_ATTEMPTS):
        report = crash_reports.newest_crash_report(bundle_id, udid, launched_epoch)
        if report or attempt == CRASH_REPORT_WAIT_ATTEMPTS - 1:
            break
        time.sleep(CRASH_REPORT_WAIT_SECONDS)
    return {"state": "app_exited", "is_app_running": False, "crash_report": report}


def launch_failure_response(action: str, platform: str, dev_id: str, package: str, check: dict,
                            **extra) -> int:
    """not_foreground / app_exited failure response. Existing codes are left untouched."""
    if check["state"] == "not_foreground":
        blocker = check.get("blocking_activity") or "(no focused window)"
        return out({"ok": False, "code": "not_foreground", "action": action, "platform": platform,
                    "device": dev_id, "package": package, "foreground_package": check.get("foreground_package"),
                    "blocking_activity": check.get("blocking_activity"),
                    "is_not_responding": check.get("is_not_responding", False),
                    "error": f"{package} did not come to the front — on top: {blocker}",
                    "summary": f"{package} {action} done, but another screen is in front",
                    "next": "Look at the covering screen with app shot. If another session owns it (device_owned_by_other) ask the user, "
                            "otherwise run app relaunch again or device reboot",
                    **extra})
    report = check.get("crash_report")
    return out({"ok": False, "code": "app_exited", "action": action, "platform": platform, "device": dev_id,
                "package": package, "crash_report": report,
                "error": f"{package} exited right after launch" + (f" — {report['exception_line']}" if report
                                                                   and report.get("exception_line") else ""),
                "summary": f"{package} exited right after {action}",
                "next": (f"Read the crash report: {report['path']}" if report else
                         "No report — see the startup log with xcrun simctl launch --console-pty"),
                **extra})
