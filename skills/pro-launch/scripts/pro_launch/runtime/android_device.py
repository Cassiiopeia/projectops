"""Android 기기 준비 상태 · 기다리기 · APK 설치 (#924).

설치 한 번이 기기가 안 깨어난 채로 수십 분 멈춘 실사고(호스트 스왑 19/20GB 에서 200MB APK 61분)가 근거다.
설치 앞에서 "기기가 답하나"를 먼저 보고, 단계마다 시간 한도를 두고, 부팅 직후의 Broken pipe 는 서비스가 돌아오길 기다려 한 번 다시 한다.
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

# 단계별 시간 한도 (초)
SHELL_PING_TIMEOUT_SECONDS = 10
SERVICE_CHECK_TIMEOUT_SECONDS = 10
PUSH_TIMEOUT_SECONDS = 300
INSTALL_TIMEOUT_SECONDS = 300
CLEANUP_TIMEOUT_SECONDS = 20
# 패키지 서비스가 돌아오기를 기다리는 한도 · 간격 (초)
PACKAGE_SERVICE_WAIT_SECONDS = 90
POLL_SECONDS = 3
# 준비 완료 판정: 이 횟수만큼 연속으로 모든 조건을 만족해야 한다 (부팅 직후 system_server 가 다시 뜨는 일이 있다)
READY_STABLE_POLLS = 3
READY_TIMEOUT_SECONDS = 300
# 기기 쪽 임시 파일 자리
DEVICE_TEMPORARY_FOLDER = "/data/local/tmp"
_PING_TOKEN = "pro-launch-ping"
# 부팅 직후 패키지 서비스가 아직 없을 때 pm 이 내는 문구
_SERVICE_NOT_READY_MARKERS = ("Broken pipe", "Can't find service", "Failure calling service package")


class AdbResult(NamedTuple):
    is_ok: bool
    text: str
    is_timeout: bool


def adb(serial: str, *arguments: str, timeout: int) -> AdbResult:
    """adb -s <serial> ... 한 번. 도구 없음 · 시간 초과도 결과로 돌려준다 (예외를 올리지 않는다)."""
    tool = sdk_tool("adb")
    if not tool:
        return AdbResult(False, "adb not found (check adb_path in doctor)", False)
    try:
        r = subprocess.run([tool, "-s", serial, *arguments], capture_output=True, text=True, timeout=timeout)
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
    """패키지 서비스가 보일 때까지 (init.svc.bootanim 은 안 본다 — 끝내 stopped 가 안 되는 기기가 있다, 실측)."""
    deadline = time.monotonic() + wait_seconds
    while True:
        if is_package_service_found(serial):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS)


def wait_until_ready(serial: str, timeout_seconds: float = READY_TIMEOUT_SECONDS,
                     stable_polls: int = READY_STABLE_POLLS) -> dict:
    """진짜 쓸 수 있을 때까지 기다린다 > {is_ready, waited_seconds, last}.

    조건 4개: 셸 응답 · 부팅 완료 · 패키지 서비스 · 초점 창이 "Not Responding" 아님 — 연속 stable_polls 회.
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
    """기기가 안 답할 때 함께 싣는 호스트 메모리 압박 — 원인이 기기가 아니라 호스트 스왑인 일이 잦다."""
    summary = host_resources.memory_summary()
    return {"resources": summary, "host_advice": host_resources.pressure_advice(summary["pressure"])}


def _unresponsive(serial: str, step: str, detail: str) -> dict:
    return {"is_ok": False, "code": "device_unresponsive", "step": step, "detail": detail,
            **host_pressure_fields(),
            "next": f"device reboot --device {serial} --cold  # force-stops the emulator and starts it again (if another session uses this device, ask before --yes)"}


def _device_file_name(apk_path: Path) -> str:
    return "pro-launch-" + re.sub(r"[^A-Za-z0-9._-]", "_", apk_path.name)


def install_apk(serial: str, apk_path: Path) -> dict:
    """APK 설치: 준비 확인 > push > pm install (부팅 직후 Broken pipe 면 서비스 대기 후 1회 재시도) > 임시 파일 삭제.

    > {is_ok, code, step, detail, retried, [resources, next]}. 실패 code: device_unresponsive · install_failed.
    """
    # 준비 확인 (셸 응답 · 패키지 서비스) — 답 없는 기기에 200MB 를 밀어 넣지 않는다
    if not is_shell_answering(serial):
        return _unresponsive(serial, "ready_check", "adb shell echo does not answer")
    if not is_package_service_found(serial) and not wait_for_package_service(serial):
        return _unresponsive(serial, "ready_check", "package service (service check package) not found")

    remote = f"{DEVICE_TEMPORARY_FOLDER}/{_device_file_name(apk_path)}"
    pushed = adb(serial, "push", str(apk_path), remote, timeout=PUSH_TIMEOUT_SECONDS)
    if pushed.is_timeout:
        return _unresponsive(serial, "push", pushed.text)
    if not pushed.is_ok:
        return {"is_ok": False, "code": "install_failed", "step": "push", "detail": pushed.text[-300:],
                "retried": False}

    retried = False
    installed = adb(serial, "shell", "pm", "install", "-r", "-t", remote, timeout=INSTALL_TIMEOUT_SECONDS)
    if not installed.is_timeout and any(m in installed.text for m in _SERVICE_NOT_READY_MARKERS):
        # 부팅 직후 서비스가 아직 안 떴다 — 돌아올 때까지 기다린 뒤 한 번만 다시
        retried = True
        if not wait_for_package_service(serial):
            return _unresponsive(serial, "install_retry", "package service did not come back after Broken pipe")
        installed = adb(serial, "shell", "pm", "install", "-r", "-t", remote, timeout=INSTALL_TIMEOUT_SECONDS)
    # 실패해도 임시 파일은 지운다 (성공·실패 공통)
    adb(serial, "shell", "rm", "-f", remote, timeout=CLEANUP_TIMEOUT_SECONDS)
    if installed.is_timeout:
        return _unresponsive(serial, "install", installed.text)
    if "Success" not in installed.text:
        return {"is_ok": False, "code": "install_failed", "step": "install", "detail": installed.text[-300:],
                "retried": retried}
    return {"is_ok": True, "code": "ok", "step": "install", "detail": "Success", "retried": retried}
