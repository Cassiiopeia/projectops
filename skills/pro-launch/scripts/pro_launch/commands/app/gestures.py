"""Shared by app tap and swipe — backend pick, before/after screen comparison, result response."""
from __future__ import annotations

import os
import time

import app_input
import knowledge
import maestro_drivers
import maestro_runs
import node_match

from pro_launch.runtime import host_resources
from pro_launch.commands.app.burst import finish_burst, start_burst
from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import no_device_response, pick_device
from pro_launch.runtime.output import out
from pro_launch.runtime.shots import finish_shot, shot_target

# Env var for the Maestro iOS driver startup wait, and its value under overload (ms) — a user-set value is kept (#922)
DRIVER_STARTUP_TIMEOUT_ENV = "MAESTRO_DRIVER_STARTUP_TIMEOUT"
OVERLOADED_DRIVER_STARTUP_TIMEOUT_MILLISECONDS = 180000
# Memory pressure level at which host status is attached to failure responses
REPORTED_MEMORY_PRESSURES = ("high", "critical")
# Recommend a session when an iOS action without a persistent session takes longer than this (seconds; about 1s with a session)
SLOW_IOS_WITHOUT_SESSION_SECONDS = 15
# session_fallback meaning there is no session at all (other reasons mean a session exists but could not be used — do not ask to start it again)
SESSION_MISSING_FALLBACKS = ("session_gone",)


def elapsed_seconds(args) -> float | None:
    """Seconds since the `app` call started. None without a start mark (tests calling the action directly)."""
    started = getattr(args, "started_monotonic", None)
    return round(time.monotonic() - started, 1) if started is not None else None


def backend_for(args):
    """(backend, device id, error response). Fills the error response if no device can be picked or the tool is missing."""
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return None, None, no_device_response(dev, args.device)
    be, err = backend_on(platform, args, dev_id)
    return be, (dev_id if be else None), err


def backend_on(platform: str, args, dev_id: str | None = None):
    """(backend, error response) — for actions that already picked a device. Fills the error response if there is no backend or tool."""
    be = app_input.get_backend(platform, getattr(args, "pkg", None) or os.environ.get("PKG"))
    if be is None:
        return None, out({"ok": False, "code": "platform_unsupported",
                          "error": f"{platform} has no control backend",
                          "next": "Add a backend following references/extending.md"})
    if not be.available():
        return None, out({"ok": False, "code": f"{be.name}_tool_missing",
                          "error": f"{be.name} control tool is missing", "next": be.install_hint})
    if be.name == "ios":
        prepare_ios_maestro(dev_id)
    return be, None


def prepare_ios_maestro(dev_id: str | None) -> None:
    """Before an iOS action: clean up orphan drivers on the same device > if overloaded, extend the driver startup wait (inherited by child maestro and relay)."""
    try:
        maestro_drivers.clean_auto(dev_id)
    except Exception:   # noqa: BLE001 — cleanup is auxiliary and must not block the action
        pass
    if DRIVER_STARTUP_TIMEOUT_ENV not in os.environ and host_resources.read_load()["is_overloaded"]:
        os.environ[DRIVER_STARTUP_TIMEOUT_ENV] = str(OVERLOADED_DRIVER_STARTUP_TIMEOUT_MILLISECONDS)


def session_fields(be) -> dict:
    """Whether the iOS persistent session was used or fell back, Maestro lock wait, auto-cleaned orphan drivers (keys absent if none)."""
    fields = dict(getattr(be, "session_report", None) or {})
    if getattr(be, "name", None) == "ios":
        fields.update(maestro_runs.lock_wait_report())
        if maestro_drivers.CLEANED_DRIVERS:
            fields["cleaned_stale_drivers"] = list(maestro_drivers.CLEANED_DRIVERS)
    return fields


def with_session_advice(result: dict, be, dev_id: str | None, args) -> dict:
    """On iOS without a persistent session past 15s, change next to app session start and move the original next to hint."""
    if getattr(be, "name", None) != "ios":
        return result
    report = getattr(be, "session_report", None) or {}
    has_no_session = not report or report.get("session_fallback") in SESSION_MISSING_FALLBACKS
    elapsed = elapsed_seconds(args)
    if not has_no_session or elapsed is None or elapsed <= SLOW_IOS_WITHOUT_SESSION_SECONDS:
        return result
    previous_next = result.get("next")
    result["next"] = (f"app session start --device {dev_id}  "
                      f"# this took {elapsed}s — with a session tap is 1s · tree 0.6s (when doing more actions)")
    result["hint"] = ("Without a resident session every iOS action starts a new Maestro (JVM)"
                      + (f" — after starting the session: {previous_next}" if previous_next else ""))
    return result


def ios_failure_fields(be, dev_id: str | None) -> dict:
    """4 diagnostics for iOS Maestro failures: leftover orphan drivers, other running Maestro, host load, Maestro's last error line."""
    if getattr(be, "name", None) != "ios":
        return {}
    fields: dict = {}
    try:
        fields.update(maestro_drivers.failure_fields(dev_id))
    except Exception:   # noqa: BLE001 — diagnostics must not spoil the failure response
        pass
    fields.update(host_load_fields())
    last_error = maestro_runs.last_error_line()
    if last_error:
        fields["backend_last_error"] = last_error
    return fields


def host_load_fields() -> dict:
    """{host_load: ...} if load exceeds twice the core count or memory pressure is high or above, else {}."""
    load = host_resources.read_load()
    memory_pressure = host_resources.memory_summary()["pressure"]
    if not load["is_overloaded"] and memory_pressure not in REPORTED_MEMORY_PRESSURES:
        return {}
    return {"host_load": {"load_1m": load["load_1m"], "load_5m": load["load_5m"], "cpu_count": load["cpu_count"],
                          "is_overloaded": load["is_overloaded"], "memory_pressure": memory_pressure,
                          "driver_startup_timeout_ms": os.environ.get(DRIVER_STARTUP_TIMEOUT_ENV)}}


def device_failure_response(be, dev_id, args=None) -> int:
    """Could not read the screen tree — code by cause (system restarting, UiAutomation connection failure, timeout, other)."""
    failure = getattr(be, "device_failure", None) or {"code": "ui_dump_failed", "reason": None}
    next_hint = {
        "android_system_not_ready": "Look at the screen with app shot. If the boot screen persists, restart the emulator (cold boot — ask the user first)",
        "ui_automation_unavailable": "Check whether another automation tool (Maestro · Appium) is using the device. Retry shortly or use an --at ratio coordinate",
        "ui_dump_timeout": "The screen may be animating continuously. Look with app shot and use an --at ratio coordinate",
    }.get(failure["code"], "Retry shortly or use an --at ratio coordinate")
    return out({"ok": False, "code": failure["code"], "device": dev_id,
                "error": failure.get("reason") or "Could not read the screen structure (it may be animating or a secure screen)",
                "elapsed_seconds": elapsed_seconds(args) if args is not None else None,
                "next": next_hint})


def before_shot(args, be, dev_id) -> bytes | None:
    """Remember the pre-action screen only with --shot — the baseline for later picking the 'changed then settled' screen. With --burst, continuous capture also starts here."""
    start_burst(args, be, dev_id)
    return be.grab(dev_id) if getattr(args, "shot", None) else None


def after_shot(args, be, dev_id, before: bytes | None) -> dict:
    """With --shot, capture the screen after the action — saves one shot call for checking.

    A fixed wait failed (measured): on Android capture is slow, so it took the same scene twice before the transition
    even started and judged it 'settled'. So we pick **once it differs from the pre-action screen and two consecutive frames match**.
    If it never changes, screen_changed=false — the agent knows right away 'tapped but no response'.
    """
    if not getattr(args, "shot", None):
        return {}
    prev, data, changed, deadline = None, None, False, time.time() + 5.0
    while time.time() < deadline:
        data = be.grab(dev_id)
        if data is None:
            return {"shot": None}
        changed = changed or (before is not None and data != before)
        if changed and data == prev:
            break
        prev = data
        time.sleep(0.3)
    raw, explicit = shot_target(project_root(args), args.shot)
    raw.write_bytes(data)
    return {"shot": str(finish_shot(raw, explicit, args)),
            "screen_changed": changed if before is not None else None}


def gesture_result(args, be, dev_id, before, ok: bool, detail: str, fail_code: str,
                    summary: str, **extra) -> int:
    diagnostics = {} if ok else ios_failure_fields(be, dev_id)
    # If the backend leaves the reason empty, use Maestro's last error line > if none, keep no reason as is (error: null is forbidden)
    error = None if ok else ((detail or "")[-400:] or diagnostics.get("backend_last_error")
                             or f"{be.name} backend failed without giving a reason")
    res = {"ok": ok, "code": "ok" if ok else fail_code, "device": dev_id, "via": be.name,
           **session_fields(be), **extra, "error": error, **diagnostics,
           "summary": summary if ok else f"Failed — {fail_code}",
           "next": "app shot  # check the resulting screen"}
    if diagnostics.get("stale_maestro_drivers"):
        res["next"] = f"app session stop --device {dev_id} --kill-stale  # clean up leftover Maestro drivers, then retry"
    if ok:
        auto_record_backend(be)
        res.update(after_shot(args, be, dev_id, before))
    res.update(finish_burst(args))
    # Make the action cost visible — on iOS each call starts a new Maestro (JVM) and takes tens of seconds (#894)
    res["elapsed_seconds"] = elapsed_seconds(args)
    if ok:
        if res.get("shot"):
            res["next"] = ("Read the shot image to check the result" if res.get("screen_changed") is not False
                           else "The screen did not change — pick another element or look again with app tree")
    # The leftover Maestro driver cleanup hint takes priority — starting a session does not fix it
    if not diagnostics.get("stale_maestro_drivers"):
        with_session_advice(res, be, dev_id, args)
    return out(res)


_BACKEND_HOW = {"android": "App taps and swipes work with launch_cli app tap/swipe (uiautomator + adb input, by screen element)",
                "ios": "App taps and swipes work with launch_cli app tap/swipe (Maestro, by screen element)"}


def auto_record_backend(be) -> None:
    """Record the action method that actually succeeded at this-computer scope — verified ones only, once a day."""
    how = _BACKEND_HOW.get(be.name)
    if how:
        try:
            knowledge.auto_record(be.name, f"{be.name}.input", how)
        except Exception:   # noqa: BLE001 — a record failure must not change the action result
            pass


def not_found_response(be, dev_id, field: str, value: str, nodes: list[dict] | None, args=None) -> int:
    """When not found, so guesses are not repeated: screen language, values actually on screen (wording from both text and desc), closest selector."""
    if nodes is None:
        nodes = be.nodes(dev_id) or []
    suggestion = node_match.did_you_mean(nodes, value)
    return out(with_session_advice({"ok": False, "code": "not_found", "device": dev_id,
                "error": f"No element with {field}={value!r} (checked text and desc, incl. doubled labels and partial matches)",
                "locale": be.locale(dev_id), "candidates": node_match.candidate_values(nodes, field),
                **({"did_you_mean": suggestion} if suggestion else {}), **session_fields(be),
                "elapsed_seconds": elapsed_seconds(args),
                "next": "app tap again with a value from candidates (text in the screen language as is)"}, be, dev_id, args))
