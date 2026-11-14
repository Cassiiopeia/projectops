"""Shared code for app control actions (launch, terminate, relaunch, permission, push, location, openurl).

Device pick, package (bundle ID) resolution, external tool runs, app launch/stop — kept here once instead of copied per action.
"""
from __future__ import annotations

import os
import subprocess

from common.proc import sdk_tool

from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import load_devices, no_device_response, pick_device
from pro_launch.runtime.output import out, set_target

# Maximum wait for one external tool run (seconds)
TOOL_TIMEOUT_SECONDS = 30


def resolve_target(args, is_package_required: bool = True):
    """(platform, device id, package, error response). Package: --pkg > $PKG > device bind package."""
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return None, None, None, no_device_response(dev, args.device)
    package = (getattr(args, "pkg", None) or os.environ.get("PKG")
               or load_devices(project_root(args))["package"])
    if is_package_required and not package:
        return platform, dev_id, None, out({
            "ok": False, "code": "package_required", "error": "No target app",
            "next": "--pkg <package name / bundle ID>  (use the value detect found)"})
    if is_package_required:
        # This action actually handles the package — values from device bind are also used to match the harness (projectops#1024)
        set_target(app=package)
    return platform, dev_id, package, None


def adb_command(dev_id: str, *args: str) -> list[str] | None:
    """adb command (always pinned with -s). None if adb is missing."""
    adb = sdk_tool("adb")
    return [adb, "-s", dev_id, *args] if adb else None


def run_tool(command: list[str] | None) -> tuple[bool, str]:
    """(success, stdout+stderr summary). Missing tool and timeout are returned as failures — no exceptions raised."""
    if not command:
        return False, "adb not found (check adb_path in doctor)"
    try:
        r = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=TOOL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return False, f"did not respond ({TOOL_TIMEOUT_SECONDS}s)"
    except OSError as e:
        return False, str(e)
    text = ((r.stdout or "") + (r.stderr or "")).replace("\r", "").strip()
    # adb shell sometimes returns device-side errors with exit code 0 (am start, pm grant)
    has_error_text = any(m in text for m in ("Error:", "Exception occurred", "Security exception"))
    return r.returncode == 0 and not has_error_text, text[-400:]


def launch_package(platform: str, dev_id: str, package: str) -> tuple[bool, str]:
    """Launch the app. Android uses monkey — no need to know the launcher activity name (am start needs it)."""
    if platform == "android":
        ok, detail = run_tool(adb_command(dev_id, "shell", "monkey", "-p", package, "-c",
                                          "android.intent.category.LAUNCHER", "1"))
        return ok and "Events injected: 1" in detail, detail
    return run_tool(["xcrun", "simctl", "launch", dev_id, package])


def terminate_package(platform: str, dev_id: str, package: str) -> tuple[bool, bool | None, str]:
    """(success, was running, reason). An app that was already stopped is not a failure."""
    if platform == "android":
        # force-stop does not say whether it was running (None = unknown)
        ok, detail = run_tool(adb_command(dev_id, "shell", "am", "force-stop", package))
        return ok, None, detail
    ok, detail = run_tool(["xcrun", "simctl", "terminate", dev_id, package])
    if not ok and "found nothing to terminate" in detail.lower():
        return True, False, ""
    return ok, ok, detail


def unsupported_response(platform: str, dev_id: str, action: str, reason: str, next_hint: str) -> int:
    """An action this platform or device cannot do — reported with one new code."""
    return out({"ok": False, "code": "unsupported_on_platform", "action": action,
                "platform": platform, "device": dev_id, "error": reason, "next": next_hint})


def control_result(action: str, platform: str, dev_id: str, ok: bool, detail: str,
                   fail_code: str, summary: str, next_ok: str, next_fail: str, **extra) -> int:
    return out({"ok": ok, "code": "ok" if ok else fail_code, "action": action,
                "platform": platform, "device": dev_id, **extra,
                "error": None if ok else (detail or "failed")[-300:],
                "summary": summary + ("" if ok else " failed"),
                "next": next_ok if ok else next_fail})
