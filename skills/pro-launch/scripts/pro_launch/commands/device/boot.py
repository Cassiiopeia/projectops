"""`device boot` / `device reboot` — boot and reboot virtual devices and wait until usable (#924 · window size).

There is one boot path (runtime/device_boot.py) — reboot --cold uses the same launcher.
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

# Seconds to wait for the device to go down after adb reboot — checking ready right away reads the pre-shutdown state
SOFT_REBOOT_DOWN_SECONDS = 6
WAIT_FOR_DEVICE_TIMEOUT_SECONDS = 180


def _window_options(args):
    """(mode, scale, error response). Validates the scale range."""
    if not device_boot.is_valid_scale(args.scale):
        return None, None, out({"ok": False, "code": "args_invalid",
                                "error": f"--scale must be {device_boot.WINDOW_SCALE_MINIMUM}–{device_boot.WINDOW_SCALE_MAXIMUM}",
                                "next": "--scale 0.4"})
    mode, scale = device_boot.resolve_window(args.window, args.scale)
    return mode, scale, None


def _unresponsive(action: str, serial: str, ready: dict, **extra) -> int:
    return out({"ok": False, "code": "device_unresponsive", "action": action, "device": serial,
                "waited_seconds": ready["waited_seconds"], "last_check": ready["last"],
                **android_device.host_pressure_fields(), **extra,
                "error": f"Not ready for use within {ready['waited_seconds']}s",
                "summary": f"{serial} not ready",
                "next": f"device reboot --device {serial} --cold  # if it was already cold, free host memory first (doctor --resources)"})


def _android_started(action: str, avd: str, launched: dict, mode: str, scale, **extra) -> int:
    """After launching the emulator: appears in adb (stop on acceleration-failure signs) > wait until ready > response."""
    serial = launched["serial"]
    appeared = device_boot.wait_for_emulator(serial, launched["log"], pid=launched.get("pid"))
    if not appeared["is_ok"]:
        if appeared["problem"]:
            device_boot.kill_emulator(serial, avd)
        return out({"ok": False, "code": "emulator_no_acceleration" if appeared["problem"] else "emulator_start_failed",
                    "action": action, "device": serial, "avd": avd, "log": launched["log"],
                    "error": appeared["problem"] or "The emulator did not appear in adb", **extra,
                    # Log tail and process liveness — judge the cause without opening the log file (#987)
                    "log_tail": appeared.get("log_tail", ""), "process_alive": appeared.get("process_alive"),
                    **android_device.host_pressure_fields(),
                    "next": f"Read the log: {launched['log']}"})
    ready = android_device.wait_until_ready(serial)
    if not ready["is_ready"]:
        return _unresponsive(action, serial, ready, avd=avd, log=launched["log"], **extra)
    return out({"action": action, "platform": "android", "device": serial, "avd": avd, "window": mode,
                "scale": scale, "waited_seconds": ready["waited_seconds"], "log": launched["log"], **extra,
                "summary": f"{serial} ({avd}) ready",
                "next": "app install --path <apk>  or  app launch"})


def _ios_result(action: str, udid: str, booted: dict, **extra) -> int:
    if not booted["is_ok"]:
        return out({"ok": False, "code": "boot_failed", "action": action, "platform": "ios", "device": udid,
                    "step": booted.get("step"), "error": booted.get("detail"), **extra,
                    **android_device.host_pressure_fields(),
                    "next": "Check the state with xcrun simctl list devices. Under memory pressure, ask the user before shutting down other devices"})
    fields = {k: booted[k] for k in ("window", "scale", "already_booted", "window_scale_pending", "window_opened",
                                     "simulator_app_running", "window_hint", "window_scale_written") if k in booted}
    return out({"action": action, "platform": "ios", "device": udid, **fields, **extra,
                "summary": f"{udid} " + ("already booted (unchanged)" if booted["already_booted"] else
                                          f"booted (window: {booted['window']})"),
                "next": "app install --path <Runner.app>  or  app launch"})


def run_boot(args) -> int:
    if not args.device:
        return out({"ok": False, "code": "args_required", "error": "--device is required",
                    "next": "device boot --device <UDID|simulator name|AVD name>  (list with devices)"})
    mode, scale, err = _window_options(args)
    if err is not None:
        return err
    # Host memory before booting a new device — when critical, only user approval (--user-approved) passes (#883 · #972)
    if not is_user_approved(args) and (failure := critical_pressure_failure("device boot", is_user_approvable=True)):
        return out(failure)
    simulators = device_boot.find_ios_simulators(args.device)
    if len(simulators) > 1:
        return out({"ok": False, "code": "device_ambiguous", "error": f"{len(simulators)} simulators are named '{args.device}'",
                    "candidates": [{"udid": s["udid"], "runtime": s["runtime"], "state": s["state"]} for s in simulators],
                    "next": "Pick one with --device <UDID>"})
    if simulators:
        udid = simulators[0]["udid"]
        if simulators[0]["state"] != "Booted" and (refusal := _budget_refusal("ios", args)) is not None:
            return refusal
        with boot_turn.boot_turn():
            booted = device_boot.boot_ios(udid, mode, scale)
        return _ios_result("boot", udid, booted, name=simulators[0]["name"])
    avds = list_devices()["android_avds"]
    if args.device not in avds:
        return out({"ok": False, "code": "no_device", "error": f"No simulator or AVD named '{args.device}'",
                    "android_avds": avds, "next": "See the list with devices and pass a name or UDID"})
    running = {avd: serial for serial, avd in device_boot.running_emulators().items()}
    if args.device in running:
        return out({"action": "boot", "platform": "android", "device": running[args.device], "avd": args.device,
                    "already_booted": True, "summary": "Already booted (unchanged)", "next": None})
    if (refusal := _budget_refusal("android", args)) is not None:
        return refusal
    with boot_turn.boot_turn():
        launched = device_boot.launch_emulator(args.device, mode, scale, args.cold)
        if not launched["is_ok"]:
            return out({"ok": False, "code": "emulator_start_failed", "error": launched["detail"],
                        "next": "Check emulator_path with doctor"})
        touch_device(launched["serial"], str(project_root(args)))
        return _android_started("boot", args.device, launched, mode, scale, already_booted=False)


def is_user_approved(args) -> bool:
    """The user saw the memory risk and said go ahead — the only flag that passes the risk gate (--yes does not)."""
    return bool(getattr(args, "user_approved", False))


def _budget_refusal(platform: str, args) -> int | None:
    """Memory budget before booting (#964) — stops without --user-approved if exceeded."""
    if is_user_approved(args):
        return None
    reason = device_capacity.boot_block_reason(platform, device_pool_facts.booted_virtual_counts())
    if reason is None:
        return None
    return out({"ok": False, "code": "device_budget_exceeded", "error": reason, "reasons": [reason],
                "capacity": device_capacity.capacity_view(), **android_device.host_pressure_fields(),
                **memory_risk_fields(),
                "next": f"Return or shut down booted devices that are not in use (device records), or {MEMORY_RISK_NEXT}"})


def run_reboot(args) -> int:
    platform, dev_id, err = resolve_device(args)
    if err is not None:
        return err
    mode, scale, err = _window_options(args)
    if err is not None:
        return err
    # Rebooting wipes that device's app state — stop without --yes on devices held by another session
    if not args.yes and (refusal := refuse_other_session_owner(dev_id, "reboot")) is not None:
        return refusal
    touch_device(dev_id, str(project_root(args)))
    if platform == "ios":
        is_down, detail = device_boot.shutdown_ios(dev_id)
        if not is_down:
            return out({"ok": False, "code": "boot_failed", "action": "reboot", "device": dev_id,
                        "step": "shutdown", "error": detail[-300:], "next": "Check the state with xcrun simctl list devices"})
        return _ios_result("reboot", dev_id, device_boot.boot_ios(dev_id, mode, scale))
    if not args.cold:
        # Soft: adb reboot > wait for it to go down and come back > ready
        android_device.adb(dev_id, "reboot", timeout=30)
        time.sleep(SOFT_REBOOT_DOWN_SECONDS)
        android_device.adb(dev_id, "wait-for-device", timeout=WAIT_FOR_DEVICE_TIMEOUT_SECONDS)
        ready = android_device.wait_until_ready(dev_id)
        if not ready["is_ready"]:
            return _unresponsive("reboot", dev_id, ready, reboot_kind="soft")
        return out({"action": "reboot", "platform": "android", "device": dev_id, "reboot_kind": "soft",
                    "waited_seconds": ready["waited_seconds"], "summary": f"{dev_id} rebooted", "next": "app launch"})
    avd = device_boot.emulator_avd_name(dev_id)
    if avd is None:
        return out({"ok": False, "code": "unsupported_on_platform", "action": "reboot", "platform": "android",
                    "device": dev_id, "error": "--cold works only for emulators (a physical device cannot be powered off)",
                    "next": "device reboot --device <serial>  # soft reboot"})
    # Power off (emu kill > force-kill qemu) > boot with -no-snapshot-load on the same port
    killed = device_boot.kill_emulator(dev_id, avd)
    if not killed["is_gone"]:
        return out({"ok": False, "code": "emulator_kill_failed", "action": "reboot", "device": dev_id, "avd": avd,
                    "forced_pids": killed["forced_pids"], "error": "qemu did not exit even after a force kill",
                    "next": "Run kill -9 <pid> yourself or restart the Mac"})
    launched = device_boot.launch_emulator(avd, mode, scale, True, port=int(dev_id.rsplit("-", 1)[1]))
    if not launched["is_ok"]:
        return out({"ok": False, "code": "emulator_start_failed", "error": launched["detail"],
                    "next": "Check emulator_path with doctor"})
    return _android_started("reboot", avd, launched, mode, scale, reboot_kind="cold", killed_by=killed["killed_by"],
                            forced_pids=killed["forced_pids"])
