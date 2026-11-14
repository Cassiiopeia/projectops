"""Android device readiness · waiting · APK install (#924).

Motivated by a real incident where one install stalled for tens of minutes with the device not awake (200MB APK took 61 min with host swap at 19/20GB).
Before installing, check "does the device answer", put a time limit on each step, and on Broken pipe right after boot wait for the service and retry once.
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import NamedTuple

from common.proc import sdk_tool

from pro_launch.runtime import host_resources
from pro_launch.runtime.foreground import read_android_foreground

# Time limit per step (s)
SHELL_PING_TIMEOUT_SECONDS = 10
SERVICE_CHECK_TIMEOUT_SECONDS = 10
PUSH_TIMEOUT_SECONDS = 300
INSTALL_TIMEOUT_SECONDS = 300
CLEANUP_TIMEOUT_SECONDS = 20
# Limit · interval for waiting until the package service comes back (s)
PACKAGE_SERVICE_WAIT_SECONDS = 90
POLL_SECONDS = 3
# Readiness verdict: all conditions must hold this many times in a row (system_server sometimes restarts right after boot)
READY_STABLE_POLLS = 3
READY_TIMEOUT_SECONDS = 300
# Device-side temp file location
DEVICE_TEMPORARY_FOLDER = "/data/local/tmp"
_PING_TOKEN = "pro-launch-ping"
# Text pm prints when the package service is not up yet right after boot
_SERVICE_NOT_READY_MARKERS = ("Broken pipe", "Can't find service", "Failure calling service package")
# Text when install fails because /data is full (#1175) — the last line is a different stack frame each time, so search everywhere
_INSUFFICIENT_STORAGE_MARKERS = ("INSUFFICIENT_STORAGE", "resolveInstallVolume", "not enough space",
                                 "no room on allowed volumes", "No space left on device")
# One cause line from pm output — earlier patterns win: Failure [...] > exception message (Exception: ...) > storage text
_FAILURE_LINE_PATTERNS = (re.compile(r"Failure \[|INSTALL_FAILED_"), re.compile(r"(Exception|Error): \S"),
                          re.compile(r"No space left", re.IGNORECASE))
# Max length of failure detail
FAILURE_DETAIL_MAX_CHARS = 300
# Warn when free space on /data is below this (MB) — one debug APK (~200MB) + the copy during install
LOW_DATA_FREE_MEGABYTES = 1024


class AdbResult(NamedTuple):
    is_ok: bool
    text: str
    is_timeout: bool


def adb(serial: str, *arguments: str, timeout: int) -> AdbResult:
    """One adb -s <serial> ... call. Missing tool · timeout are also returned as results (no exceptions raised)."""
    tool = sdk_tool("adb")
    if not tool:
        return AdbResult(False, "adb not found (check adb_path in doctor)", False)
    try:
        r = subprocess.run([tool, "-s", serial, *arguments], capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return AdbResult(False, f"no response ({timeout}s)", True)
    except OSError as error:
        return AdbResult(False, str(error), False)
    text = ((r.stdout or "") + (r.stderr or "")).replace("\r", "").strip()
    return AdbResult(r.returncode == 0, text, False)


def is_shell_answering(serial: str) -> bool:
    result = adb(serial, "shell", "echo", _PING_TOKEN, timeout=SHELL_PING_TIMEOUT_SECONDS)
    return result.is_ok and _PING_TOKEN in result.text


def is_package_service_found(serial: str) -> bool:
    result = adb(serial, "shell", "service", "check", "package", timeout=SERVICE_CHECK_TIMEOUT_SECONDS)
    return "Service package: found" in result.text


def is_boot_completed(serial: str) -> bool:
    result = adb(serial, "shell", "getprop", "sys.boot_completed", timeout=SERVICE_CHECK_TIMEOUT_SECONDS)
    return result.text.strip() == "1"


def wait_for_package_service(serial: str, wait_seconds: float = PACKAGE_SERVICE_WAIT_SECONDS) -> bool:
    """Until the package service is visible (init.svc.bootanim is not checked — some devices never reach stopped, observed)."""
    deadline = time.monotonic() + wait_seconds
    while True:
        if is_package_service_found(serial):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS)


def wait_until_ready(serial: str, timeout_seconds: float = READY_TIMEOUT_SECONDS,
                     stable_polls: int = READY_STABLE_POLLS) -> dict:
    """Wait until truly usable > {is_ready, waited_seconds, last}.

    4 conditions: shell answers · boot completed · package service · focused window is not "Not Responding" — stable_polls times in a row.
    """
    started = time.monotonic()
    consecutive = 0
    last: dict = {}
    while True:
        last = {"shell": is_shell_answering(serial)}
        if last["shell"]:
            last["boot_completed"] = is_boot_completed(serial)
            last["package_service"] = last["boot_completed"] and is_package_service_found(serial)
            if last["package_service"]:
                last["not_responding"] = read_android_foreground(serial)["is_not_responding"]
        is_now_ready = bool(last.get("package_service")) and not last.get("not_responding")
        consecutive = consecutive + 1 if is_now_ready else 0
        if consecutive >= stable_polls:
            return {"is_ready": True, "waited_seconds": round(time.monotonic() - started, 1), "last": last}
        if time.monotonic() - started >= timeout_seconds:
            return {"is_ready": False, "waited_seconds": round(time.monotonic() - started, 1), "last": last}
        time.sleep(POLL_SECONDS)


def host_pressure_fields() -> dict:
    """Host memory pressure attached when the device does not answer — the cause is often host swap, not the device."""
    summary = host_resources.memory_summary()
    return {"resources": summary, "host_advice": host_resources.pressure_advice(summary["pressure"])}


def _unresponsive(serial: str, step: str, detail: str) -> dict:
    return {"is_ok": False, "code": "device_unresponsive", "step": step, "detail": detail,
            **host_pressure_fields(),
            "next": f"device reboot --device {serial} --cold  # force-stops the emulator and starts it again (if another session uses this device, ask before --yes)"}


def read_data_storage(serial: str) -> dict | None:
    """Device /data space (df -k) > {free_megabytes, total_megabytes, used_percent, is_low}. None if unreadable"""
    result = adb(serial, "shell", "df", "-k", "/data", timeout=SERVICE_CHECK_TIMEOUT_SECONDS)
    if not result.is_ok:
        return None
    # Last line: device 1K-blocks Used Available Use% mount
    fields = result.text.splitlines()[-1].split() if result.text else []
    if len(fields) < 5 or not (fields[1].isdigit() and fields[3].isdigit()):
        return None
    total_kilobytes, free_kilobytes = int(fields[1]), int(fields[3])
    free_megabytes = free_kilobytes // 1024
    return {"free_megabytes": free_megabytes, "total_megabytes": total_kilobytes // 1024,
            "used_percent": round(100 - free_kilobytes * 100 / total_kilobytes) if total_kilobytes else None,
            "is_low": free_megabytes < LOW_DATA_FREE_MEGABYTES}


def low_storage_next(serial: str) -> str:
    return (f"Free space on {serial}: uninstall old builds (adb -s {serial} uninstall <package>), "
            "or borrow a fresh device: device acquire --platform android --fresh")


def _failure_detail(text: str) -> str:
    """pm output > cause line (Failure [...] · exception text) first, otherwise the tail"""
    lines = text.splitlines()
    for pattern in _FAILURE_LINE_PATTERNS:
        found = next((line.strip() for line in lines if pattern.search(line)), None)
        if found:
            return found[:FAILURE_DETAIL_MAX_CHARS]
    return text[-FAILURE_DETAIL_MAX_CHARS:]


def _install_failure(serial: str, step: str, text: str, has_retried: bool) -> dict:
    """push · install failure > insufficient_storage + /data space if out of storage, otherwise install_failed"""
    failure = {"is_ok": False, "code": "install_failed", "step": step, "detail": _failure_detail(text),
               "retried": has_retried}
    if any(marker.lower() in text.lower() for marker in _INSUFFICIENT_STORAGE_MARKERS):
        failure.update(code="insufficient_storage", data_storage=read_data_storage(serial),
                       next=low_storage_next(serial))
    return failure


def _device_file_name(apk_path: Path) -> str:
    return "pro-launch-" + re.sub(r"[^A-Za-z0-9._-]", "_", apk_path.name)


def install_apk(serial: str, apk_path: Path) -> dict:
    """APK install: readiness check > push > pm install (on Broken pipe right after boot, wait for the service and retry once) > delete temp file.

    > {is_ok, code, step, detail, retried, [resources, data_storage, next]}.
    Failure codes: device_unresponsive · insufficient_storage · install_failed.
    """
    # Readiness check (shell answers · package service) — do not push 200MB into a device that does not answer
    if not is_shell_answering(serial):
        return _unresponsive(serial, "ready_check", "adb shell echo does not answer")
    if not is_package_service_found(serial) and not wait_for_package_service(serial):
        return _unresponsive(serial, "ready_check", "package service (service check package) not found")

    remote = f"{DEVICE_TEMPORARY_FOLDER}/{_device_file_name(apk_path)}"
    pushed = adb(serial, "push", str(apk_path), remote, timeout=PUSH_TIMEOUT_SECONDS)
    if pushed.is_timeout:
        return _unresponsive(serial, "push", pushed.text)
    if not pushed.is_ok:
        return _install_failure(serial, "push", pushed.text, has_retried=False)

    has_retried = False
    installed = adb(serial, "shell", "pm", "install", "-r", "-t", remote, timeout=INSTALL_TIMEOUT_SECONDS)
    if not installed.is_timeout and any(m in installed.text for m in _SERVICE_NOT_READY_MARKERS):
        # Service not up yet right after boot — wait until it returns, then retry just once
        has_retried = True
        if not wait_for_package_service(serial):
            return _unresponsive(serial, "install_retry", "package service did not come back after Broken pipe")
        installed = adb(serial, "shell", "pm", "install", "-r", "-t", remote, timeout=INSTALL_TIMEOUT_SECONDS)
    # Delete the temp file even on failure (success·failure alike)
    adb(serial, "shell", "rm", "-f", remote, timeout=CLEANUP_TIMEOUT_SECONDS)
    if installed.is_timeout:
        return _unresponsive(serial, "install", installed.text)
    if "Success" not in installed.text:
        return _install_failure(serial, "install", installed.text, has_retried)
    return {"is_ok": True, "code": "ok", "step": "install", "detail": "Success", "retried": has_retried}
