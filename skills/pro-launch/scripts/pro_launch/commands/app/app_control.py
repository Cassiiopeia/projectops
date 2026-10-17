"""app 의 앱 제어 동작(launch · terminate · relaunch · permission · push · location · openurl)이 함께 쓰는 것.

기기 고르기 · 패키지(번들 ID) 해석 · 외부 도구 실행 · 앱 띄우기/끄기 — 동작마다 복사하지 않고 여기 하나에 둔다.
"""
from __future__ import annotations

import os
import subprocess

from common.proc import sdk_tool

from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import load_devices, no_device_response, pick_device
from pro_launch.runtime.output import out

# 외부 도구 한 번의 최대 대기 (초)
TOOL_TIMEOUT_SECONDS = 30


def resolve_target(args, is_package_required: bool = True):
    """(플랫폼, 기기 id, 패키지, 오류 응답). 패키지: --pkg > $PKG > device bind 의 package."""
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return None, None, None, no_device_response(dev, args.device)
    package = (getattr(args, "pkg", None) or os.environ.get("PKG")
               or load_devices(project_root(args))["package"])
    if is_package_required and not package:
        return platform, dev_id, None, out({
            "ok": False, "code": "package_required", "error": "대상 앱을 모릅니다",
            "next": "--pkg <패키지명·번들ID>  (detect 가 찾은 값을 쓰세요)"})
    return platform, dev_id, package, None


def adb_command(dev_id: str, *args: str) -> list[str] | None:
    """adb 명령 (항상 -s 로 기기 고정). adb 가 없으면 None."""
    adb = sdk_tool("adb")
    return [adb, "-s", dev_id, *args] if adb else None


def run_tool(command: list[str] | None) -> tuple[bool, str]:
    """(성공 여부, stdout+stderr 요약). 도구 없음·시간 초과도 실패로 돌려준다 — 예외를 올리지 않는다."""
    if not command:
        return False, "adb 를 찾지 못했다 (doctor 의 adb_path 확인)"
    try:
        r = subprocess.run(command, capture_output=True, text=True, timeout=TOOL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return False, f"응답 없음 ({TOOL_TIMEOUT_SECONDS}초)"
    except OSError as e:
        return False, str(e)
    text = ((r.stdout or "") + (r.stderr or "")).replace("\r", "").strip()
    # adb shell 은 기기 쪽 오류를 종료코드 0 으로 돌려주는 일이 있다 (am start · pm grant)
    has_error_text = any(m in text for m in ("Error:", "Exception occurred", "Security exception"))
    return r.returncode == 0 and not has_error_text, text[-400:]


def launch_package(platform: str, dev_id: str, package: str) -> tuple[bool, str]:
    """앱 띄우기. Android 는 monkey — 런처 액티비티 이름을 몰라도 된다 (am start 는 알아야 한다)."""
    if platform == "android":
        ok, detail = run_tool(adb_command(dev_id, "shell", "monkey", "-p", package, "-c",
                                          "android.intent.category.LAUNCHER", "1"))
        return ok and "Events injected: 1" in detail, detail
    return run_tool(["xcrun", "simctl", "launch", dev_id, package])


def terminate_package(platform: str, dev_id: str, package: str) -> tuple[bool, bool | None, str]:
    """(성공 여부, 떠 있었나, 사유). 이미 꺼져 있던 것은 실패가 아니다."""
    if platform == "android":
        # force-stop 은 떠 있었는지 알려 주지 않는다 (None = 모름)
        ok, detail = run_tool(adb_command(dev_id, "shell", "am", "force-stop", package))
        return ok, None, detail
    ok, detail = run_tool(["xcrun", "simctl", "terminate", dev_id, package])
    if not ok and "found nothing to terminate" in detail.lower():
        return True, False, ""
    return ok, ok, detail


def unsupported_response(platform: str, dev_id: str, action: str, reason: str, next_hint: str) -> int:
    """이 플랫폼·기기에서는 할 수 없는 동작 — 새 code 하나로 알린다."""
    return out({"ok": False, "code": "unsupported_on_platform", "action": action,
                "platform": platform, "device": dev_id, "error": reason, "next": next_hint})


def control_result(action: str, platform: str, dev_id: str, ok: bool, detail: str,
                   fail_code: str, summary: str, next_ok: str, next_fail: str, **extra) -> int:
    return out({"ok": ok, "code": "ok" if ok else fail_code, "action": action,
                "platform": platform, "device": dev_id, **extra,
                "error": None if ok else (detail or "실패")[-300:],
                "summary": summary + ("" if ok else " 실패"),
                "next": next_ok if ok else next_fail})
