"""`device boot` · `device reboot` — 가상 기기를 띄우고 다시 띄운다. 쓸 수 있을 때까지 기다린다 (#924 · 창 크기).

띄우는 길은 하나(runtime/device_boot.py)다 — reboot --cold 도 같은 launcher 를 쓴다.
"""
from __future__ import annotations

import time

from pro_launch.commands.device.claims import refuse_other_session_owner, resolve_device
from pro_launch.runtime import android_device, boot_turn, device_boot, device_capacity, device_pool_facts
from pro_launch.runtime.context import project_root
from pro_launch.runtime.device_claims import touch_device
from pro_launch.runtime.devices import list_devices
from pro_launch.runtime.host_resources import MEMORY_RISK_NEXT, critical_pressure_failure, memory_risk_fields
from pro_launch.runtime.output import out

# adb reboot 뒤 기기가 내려가기를 기다리는 시간 (초) — 바로 ready 를 보면 내려가기 전 상태를 읽는다
SOFT_REBOOT_DOWN_SECONDS = 6
WAIT_FOR_DEVICE_TIMEOUT_SECONDS = 180


def _window_options(args):
    """(모드, 배율, 오류 응답). 배율 범위를 검사한다."""
    if not device_boot.is_valid_scale(args.scale):
        return None, None, out({"ok": False, "code": "args_invalid",
                                "error": f"--scale 은 {device_boot.WINDOW_SCALE_MINIMUM}~{device_boot.WINDOW_SCALE_MAXIMUM}",
                                "next": "--scale 0.4"})
    mode, scale = device_boot.resolve_window(args.window, args.scale)
    return mode, scale, None


def _unresponsive(action: str, serial: str, ready: dict, **extra) -> int:
    return out({"ok": False, "code": "device_unresponsive", "action": action, "device": serial,
                "waited_seconds": ready["waited_seconds"], "last_check": ready["last"],
                **android_device.host_pressure_fields(), **extra,
                "error": f"{ready['waited_seconds']}초 안에 쓸 수 있는 상태가 되지 않았다",
                "summary": f"{serial} 준비 안 됨",
                "next": f"device reboot --device {serial} --cold  # 이미 cold 였다면 호스트 메모리를 먼저 확보한다 (doctor --resources)"})


def _android_started(action: str, avd: str, launched: dict, mode: str, scale, **extra) -> int:
    """에뮬레이터를 띄운 뒤: adb 에 나타남(가속 실패 징후면 끄고 끝) > 준비 완료 대기 > 응답."""
    serial = launched["serial"]
    appeared = device_boot.wait_for_emulator(serial, launched["log"])
    if not appeared["is_ok"]:
        if appeared["problem"]:
            device_boot.kill_emulator(serial, avd)
        return out({"ok": False, "code": "emulator_no_acceleration" if appeared["problem"] else "emulator_start_failed",
                    "action": action, "device": serial, "avd": avd, "log": launched["log"],
                    "error": appeared["problem"] or "에뮬레이터가 adb 에 나타나지 않았다", **extra,
                    **android_device.host_pressure_fields(),
                    "next": f"로그를 본다: {launched['log']}"})
    ready = android_device.wait_until_ready(serial)
    if not ready["is_ready"]:
        return _unresponsive(action, serial, ready, avd=avd, log=launched["log"], **extra)
    return out({"action": action, "platform": "android", "device": serial, "avd": avd, "window": mode,
                "scale": scale, "waited_seconds": ready["waited_seconds"], "log": launched["log"], **extra,
                "summary": f"{serial} ({avd}) 준비 완료",
                "next": "app install --path <apk>  또는  app launch"})


def _ios_result(action: str, udid: str, booted: dict, **extra) -> int:
    if not booted["is_ok"]:
        return out({"ok": False, "code": "boot_failed", "action": action, "platform": "ios", "device": udid,
                    "step": booted.get("step"), "error": booted.get("detail"), **extra,
                    **android_device.host_pressure_fields(),
                    "next": "xcrun simctl list devices 로 상태를 본다. 메모리 압박이면 다른 기기를 끄기 전에 사용자에게 묻는다"})
    fields = {k: booted[k] for k in ("window", "scale", "already_booted", "window_scale_pending", "window_opened",
                                     "simulator_app_running", "window_hint", "window_scale_written") if k in booted}
    return out({"action": action, "platform": "ios", "device": udid, **fields, **extra,
                "summary": f"{udid} " + ("이미 켜져 있다 (바꾸지 않았다)" if booted["already_booted"] else
                                          f"부팅 완료 (창: {booted['window']})"),
                "next": "app install --path <Runner.app>  또는  app launch"})


def run_boot(args) -> int:
    if not args.device:
        return out({"ok": False, "code": "args_required", "error": "--device 가 필요합니다",
                    "next": "device boot --device <UDID|시뮬레이터 이름|AVD 이름>  (devices 로 목록)"})
    mode, scale, err = _window_options(args)
    if err is not None:
        return err
    # 새 기기를 띄우기 전 호스트 메모리 — critical 이면 사용자 승인(--user-approved)만 넘는다 (#883 · #972)
    if not is_user_approved(args) and (failure := critical_pressure_failure("device boot", is_user_approvable=True)):
        return out(failure)
    simulators = device_boot.find_ios_simulators(args.device)
    if len(simulators) > 1:
        return out({"ok": False, "code": "device_ambiguous", "error": f"'{args.device}' 이름의 시뮬레이터가 {len(simulators)}개",
                    "candidates": [{"udid": s["udid"], "runtime": s["runtime"], "state": s["state"]} for s in simulators],
                    "next": "--device <UDID> 로 하나를 고른다"})
    if simulators:
        udid = simulators[0]["udid"]
        if simulators[0]["state"] != "Booted" and (refusal := _budget_refusal("ios", args)) is not None:
            return refusal
        with boot_turn.boot_turn():
            booted = device_boot.boot_ios(udid, mode, scale)
        return _ios_result("boot", udid, booted, name=simulators[0]["name"])
    avds = list_devices()["android_avds"]
    if args.device not in avds:
        return out({"ok": False, "code": "no_device", "error": f"'{args.device}' 시뮬레이터·AVD 를 찾지 못했습니다",
                    "android_avds": avds, "next": "devices 로 목록을 보고 이름이나 UDID 를 준다"})
    running = {avd: serial for serial, avd in device_boot.running_emulators().items()}
    if args.device in running:
        return out({"action": "boot", "platform": "android", "device": running[args.device], "avd": args.device,
                    "already_booted": True, "summary": "이미 켜져 있다 (바꾸지 않았다)", "next": None})
    if (refusal := _budget_refusal("android", args)) is not None:
        return refusal
    with boot_turn.boot_turn():
        launched = device_boot.launch_emulator(args.device, mode, scale, args.cold)
        if not launched["is_ok"]:
            return out({"ok": False, "code": "emulator_start_failed", "error": launched["detail"],
                        "next": "doctor 로 emulator_path 를 확인한다"})
        touch_device(launched["serial"], str(project_root(args)))
        return _android_started("boot", args.device, launched, mode, scale, already_booted=False)


def is_user_approved(args) -> bool:
    """사용자가 메모리 위험을 보고 진행하라고 답했다 — 위험 게이트를 넘는 유일한 표시 (--yes 는 넘지 않는다)."""
    return bool(getattr(args, "user_approved", False))


def _budget_refusal(platform: str, args) -> int | None:
    """새로 켜기 전 메모리 예산 (#964) — 넘으면 --user-approved 없이 멈춘다."""
    if is_user_approved(args):
        return None
    reason = device_capacity.boot_block_reason(platform, device_pool_facts.booted_virtual_counts())
    if reason is None:
        return None
    return out({"ok": False, "code": "device_budget_exceeded", "error": reason, "reasons": [reason],
                "capacity": device_capacity.capacity_view(), **android_device.host_pressure_fields(),
                **memory_risk_fields(),
                "next": f"켜져 있는 기기 중 안 쓰는 것을 반납·종료하거나(device records), {MEMORY_RISK_NEXT}"})


def run_reboot(args) -> int:
    platform, dev_id, err = resolve_device(args)
    if err is not None:
        return err
    mode, scale, err = _window_options(args)
    if err is not None:
        return err
    # 다시 켜면 그 기기의 앱 상태가 사라진다 — 다른 세션이 쥔 기기는 --yes 없이 멈춘다
    if not args.yes and (refusal := refuse_other_session_owner(dev_id, "reboot")) is not None:
        return refusal
    touch_device(dev_id, str(project_root(args)))
    if platform == "ios":
        is_down, detail = device_boot.shutdown_ios(dev_id)
        if not is_down:
            return out({"ok": False, "code": "boot_failed", "action": "reboot", "device": dev_id,
                        "step": "shutdown", "error": detail[-300:], "next": "xcrun simctl list devices 로 상태를 본다"})
        return _ios_result("reboot", dev_id, device_boot.boot_ios(dev_id, mode, scale))
    if not args.cold:
        # 소프트: adb reboot > 내려갔다 올라오기를 기다림 > 준비 완료
        android_device.adb(dev_id, "reboot", timeout=30)
        time.sleep(SOFT_REBOOT_DOWN_SECONDS)
        android_device.adb(dev_id, "wait-for-device", timeout=WAIT_FOR_DEVICE_TIMEOUT_SECONDS)
        ready = android_device.wait_until_ready(dev_id)
        if not ready["is_ready"]:
            return _unresponsive("reboot", dev_id, ready, reboot_kind="soft")
        return out({"action": "reboot", "platform": "android", "device": dev_id, "reboot_kind": "soft",
                    "waited_seconds": ready["waited_seconds"], "summary": f"{dev_id} 재부팅 완료", "next": "app launch"})
    avd = device_boot.emulator_avd_name(dev_id)
    if avd is None:
        return out({"ok": False, "code": "unsupported_on_platform", "action": "reboot", "platform": "android",
                    "device": dev_id, "error": "--cold 는 에뮬레이터만 된다 (실기기는 끌 수 없다)",
                    "next": "device reboot --device <시리얼>  # 소프트 재부팅"})
    # 끄기(emu kill > qemu 강제 종료) > 같은 포트로 -no-snapshot-load 부팅
    killed = device_boot.kill_emulator(dev_id, avd)
    if not killed["is_gone"]:
        return out({"ok": False, "code": "emulator_kill_failed", "action": "reboot", "device": dev_id, "avd": avd,
                    "forced_pids": killed["forced_pids"], "error": "qemu 가 강제 종료로도 끝나지 않았다",
                    "next": "kill -9 <pid> 를 직접 쓰거나 맥을 다시 시작한다"})
    launched = device_boot.launch_emulator(avd, mode, scale, True, port=int(dev_id.rsplit("-", 1)[1]))
    if not launched["is_ok"]:
        return out({"ok": False, "code": "emulator_start_failed", "error": launched["detail"],
                    "next": "doctor 로 emulator_path 를 확인한다"})
    return _android_started("reboot", avd, launched, mode, scale, reboot_kind="cold", killed_by=killed["killed_by"],
                            forced_pids=killed["forced_pids"])
