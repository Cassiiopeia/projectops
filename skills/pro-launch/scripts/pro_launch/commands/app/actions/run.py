"""`app run` — run several steps at once (#894).

On iOS each call starts a new Maestro (JVM), so one tap takes tens of seconds. Bundling steps into one flow starts Maestro once.
On Android the same step file runs in order through the existing backend methods (one step file across platforms).
"""
from __future__ import annotations

import os
import time
from contextlib import ExitStack

import app_input
import credentials

from pro_launch.commands.app import android_ime
from pro_launch.commands.app import steps as steps_module
from pro_launch.commands.app.gestures import (after_shot, auto_record_backend, backend_for, before_shot,
                                              elapsed_seconds, session_fields)
from pro_launch.commands.app.burst import burst_spec, finish_burst
from pro_launch.registry import Action
from pro_launch.runtime.creds import cred_field
from pro_launch.runtime.output import out

# One Maestro run's wait: startup margin + per-step margin + sum of wait-step times (seconds)
MAESTRO_STARTUP_SECONDS = 60
MAESTRO_SECONDS_PER_STEP = 15
# Screen re-read interval for Android wait (seconds)
ANDROID_WAIT_POLL_SECONDS = 0.5
# Number of Maestro output lines kept as the failure cause
FAILURE_DETAIL_LINE_COUNT = 6


def _app_run(args) -> int:
    """Run a step file: validate > device and backend > extract input values > run (iOS one flow, Android in order) > result."""
    try:
        steps = steps_module.load_steps(getattr(args, "steps", None))
    except steps_module.StepsError as e:
        return out({"ok": False, "code": "bad_steps", "step_index": e.step_index, "error": str(e),
                    "next": "See 'app run' in references/app.md for the step shape"})
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    rejection = _platform_rejection(be, steps)
    if rejection:
        return out(rejection)
    secrets, rejection = _resolve_secrets(steps, be)
    if rejection:
        return out(rejection)

    before = before_shot(args, be, dev_id)
    if be.selects_itself and not secrets and be.has_session(dev_id):
        is_success, results, detail = _run_each_step_in_session(be, dev_id, steps)
    elif be.selects_itself:
        is_success, results, detail = _run_in_one_flow(be, dev_id, steps, secrets)
    else:
        is_success, results, detail = _run_step_by_step(be, dev_id, steps, secrets,
                                                        getattr(args, "ime", None) or "auto")
    return _run_result(args, be, dev_id, before, steps, is_success, results, _mask(detail, secrets))


def _platform_rejection(be, steps: list[dict]) -> dict | None:
    """Steps this platform cannot do > reject before running (so it does not stop halfway)."""
    for index, step in enumerate(steps):
        if step["kind"] == "back" and not be.has_back_button:
            return {"ok": False, "code": "step_unsupported_on_platform", "step_index": index,
                    "platform": be.name, "error": f"{be.name} has no back button (no back step)",
                    "next": 'Press the on-screen back button with {"tap": {...}} or '
                            '{"swipe": {"from": "0.02,0.5", "to": "0.8,0.5"}} (edge swipe)'}
    return None


def _resolve_secrets(steps: list[dict], be) -> tuple[dict[int, str], dict | None]:
    """Extract values for type steps (environment variables, stored credentials) > {step number: value}. Values never leave this dict."""
    secrets: dict[int, str] = {}
    for index, step in enumerate(steps):
        if step["kind"] != "type":
            continue
        if step["env"]:
            if step["env"] not in os.environ:
                return {}, {"ok": False, "code": "env_not_set", "step_index": index,
                            "error": f"Environment variable {step['env']} is empty"}
            value = os.environ[step["env"]]
        else:
            value, err = cred_field(step["cred"], step["field"])
            if err:
                return {}, {**err, "step_index": index}
        if be.name == "android" and not value.isascii():
            return {}, {"ok": False, "code": "non_ascii_unsupported", "step_index": index,
                        "error": "adb input text accepts ASCII only (no Korean)",
                        "next": "Use an ASCII letters/digits value, or install an IME such as ADBKeyboard"}
        secrets[index] = value
    return secrets, None


def _mask(text: str, secrets: dict[int, str]) -> str:
    # Maestro prints values placed in inputText descriptions verbatim — mask them before they reach output or errors
    for value in secrets.values():
        text = credentials.mask(text, {"password": value})
    return text


# ── iOS: one Maestro run ─────────────────────────────────────────────────

def _run_in_one_flow(be, dev_id: str, steps: list[dict],
                     secrets: dict[int, str]) -> tuple[bool, list[dict], str]:
    """All steps > one flow > one Maestro run. Per-step results are split by the '... COMPLETED|FAILED' lines of Maestro output."""
    commands_per_step = [steps_module.to_maestro_commands(step, index) for index, step in enumerate(steps)]
    flow_commands = [command for commands in commands_per_step for command in commands]
    environment = {steps_module.STEP_TEXT_ENV_FORMAT.format(index=index): value
                   for index, value in secrets.items()}
    be.timeout = (MAESTRO_STARTUP_SECONDS + MAESTRO_SECONDS_PER_STEP * len(steps)
                  + sum(step.get("timeout", 0) for step in steps if step["kind"] == "wait"))
    is_success, lines = be.run_flow(dev_id, flow_commands, environment or None)
    statuses = steps_module.maestro_statuses(lines)
    per_step = steps_module.step_statuses([len(c) for c in commands_per_step], statuses)
    if is_success:
        per_step = ["completed"] * len(steps)
    elif "failed" not in per_step:
        # Output does not say where it stopped (start failure, timeout) — keep only finished steps, the rest are unknown
        per_step = [s if s == "completed" else "unknown" for s in per_step]
    results = [{"status": status} for status in per_step]
    if is_success:
        return True, results, ""
    reason = [l for l in lines if "FAILED" in l or "not found" in l.lower() or "Error" in l
              or "Assertion" in l or "did not respond" in l]
    return False, results, "\n".join((reason or lines)[-FAILURE_DETAIL_LINE_COUNT:])


# ── iOS persistent session: one run per step (#894 phase 2) ──────────────

def _run_each_step_in_session(be, dev_id: str, steps: list[dict]) -> tuple[bool, list[dict], str]:
    """A session run gives no per-step status — calling once per step (about 1s each) shows exactly which step failed.

    If the session drops midway (that step already ran via the per-call path), the remaining steps run together as one flow.
    """
    results: list[dict] = []
    for index, step in enumerate(steps):
        started = time.monotonic()
        be.timeout = MAESTRO_STARTUP_SECONDS + MAESTRO_SECONDS_PER_STEP + int(step.get("timeout", 0))
        is_success, lines = be.run_flow(dev_id, steps_module.to_maestro_commands(step, index))
        results.append({"status": "completed" if is_success else "failed",
                        "elapsed_seconds": round(time.monotonic() - started, 1)})
        if not is_success:
            results += [{"status": "not_run"} for _ in steps[index + 1:]]
            return False, results, "\n".join(lines[-FAILURE_DETAIL_LINE_COUNT:])
        remaining = steps[index + 1:]
        if remaining and be.session_report.get("session_fallback"):
            is_rest_success, rest_results, detail = _run_in_one_flow(be, dev_id, remaining, {})
            return is_rest_success, results + rest_results, detail
    return True, results, ""


# ── Android: in order ────────────────────────────────────────────────────

def _run_step_by_step(be, dev_id: str, steps: list[dict], secrets: dict[int, str],
                      ime_mode: str = "auto") -> tuple[bool, list[dict], str]:
    """Run steps one by one. Stop at the first failure; the rest are not_run. IME switch happens once at the first type step and is restored at the end."""
    with ExitStack() as input_method_stack:
        return _run_steps_in_order(be, dev_id, steps, secrets, ime_mode, input_method_stack)


def _run_steps_in_order(be, dev_id: str, steps: list[dict], secrets: dict[int, str], ime_mode: str,
                        input_method_stack: ExitStack) -> tuple[bool, list[dict], str]:
    results: list[dict] = []
    is_input_method_ready = False
    for index, step in enumerate(steps):
        started = time.monotonic()
        if step["kind"] == "type" and not is_input_method_ready:
            input_method_stack.enter_context(
                android_ime.ascii_input_method(android_ime.android_shell(be, dev_id), ime_mode, dev_id))
            is_input_method_ready = True
        is_success, detail, verification = _android_step(be, dev_id, step, secrets.get(index))
        results.append({"status": "completed" if is_success else "failed",
                        "elapsed_seconds": round(time.monotonic() - started, 1),
                        **({"verification": verification["verification"]} if verification else {})})
        if not is_success:
            results += [{"status": "not_run"} for _ in steps[index + 1:]]
            # The device may be the cause, not the step (during a system restart, wm size and input also fail)
            if not be.device_failure:
                be.device_failure = be.system_readiness_failure(dev_id)
            return False, results, detail
    return True, results, ""


def _android_step(be, dev_id: str, step: dict, value: str | None) -> tuple[bool, str, dict]:
    """One step > (success, reason, field check result for type steps)."""
    if step["kind"] == "type":
        # Treat every step file value as secret — put no visible characters in the check result
        is_success, detail, verification = android_ime.type_and_verify(be, dev_id, value, True, step["submit"])
        if detail == "typed_text_mismatch":
            detail = (f"typed_text_mismatch: the field text differs from the typed value (expected {verification['expected_length']} chars, "
                      f"visible {verification['visible_length']}) — clear the field and run again with --ime ascii")
        return is_success, detail, verification
    return (*_android_non_type_step(be, dev_id, step), {})


def _android_non_type_step(be, dev_id: str, step: dict) -> tuple[bool, str]:
    kind = step["kind"]
    if kind == "tap" and "point" in step:
        return be.tap_ratio(dev_id, *step["point"])
    if kind == "tap":
        nodes = be.nodes(dev_id) or []
        if not nodes and be.device_failure:
            return False, f"{be.device_failure['code']}: {be.device_failure['reason']}"
        found = app_input.match_nodes(nodes, step["field"], step["value"])
        if len(found) <= step["index"]:
            return False, f"No element with {step['field']}={step['value']!r} (matches: {len(found)})"
        return be.tap_xy(dev_id, *found[step["index"]]["center"])
    if kind == "swipe":
        return be.swipe_ratio(dev_id, step["start"], step["end"], step["ms"])
    if kind == "wait":
        return _android_wait(be, dev_id, step)
    return be.press_back(dev_id)


def _android_wait(be, dev_id: str, step: dict) -> tuple[bool, str]:
    """Re-read the screen tree until the element is visible (or gone with gone) (up to timeout seconds)."""
    deadline = time.monotonic() + step["timeout"]
    should_be_gone = step.get("gone", False)
    while True:
        nodes = be.nodes(dev_id) or []
        is_visible = bool(app_input.match_nodes(nodes, step["field"], step["value"]))
        # Failing to read the screen tree does not mean 'gone'
        if (is_visible and not should_be_gone) or (should_be_gone and nodes and not is_visible):
            return True, ""
        if time.monotonic() >= deadline:
            # If the screen tree could not be read at all, report that cause rather than 'not visible'
            if be.device_failure:
                return False, f"{be.device_failure['code']}: {be.device_failure['reason']}"
            if should_be_gone:
                return False, f"{step['field']}={step['value']!r} did not disappear within {step['timeout']}s"
            return False, f"{step['field']}={step['value']!r} did not appear within {step['timeout']}s"
        time.sleep(ANDROID_WAIT_POLL_SECONDS)


# ── Result ───────────────────────────────────────────────────────────────

def _run_result(args, be, dev_id: str, before, steps: list[dict], is_success: bool,
                results: list[dict], detail: str) -> int:
    """Per-step results + overall result > one JSON. --shot captures only when everything succeeded."""
    for index, (step, result) in enumerate(zip(steps, results)):
        result.update(index=index, step=steps_module.step_label(step))
    completed_count = sum(1 for r in results if r["status"] == "completed")
    failed_step = next((r["index"] for r in results if r["status"] == "failed"), None)
    payload = {"ok": is_success, "code": "ok" if is_success else "step_failed", "device": dev_id,
               "via": be.name, **session_fields(be), **_cause_of(be, is_success), "steps_total": len(steps), "steps_completed": completed_count,
               "failed_step": failed_step,
               "steps": [{k: r[k] for k in ("index", "step", "status", "elapsed_seconds", "verification") if k in r}
                         for r in results],
               "error": None if is_success else (detail or "failed")[-400:]}
    if is_success:
        auto_record_backend(be)
        payload.update(after_shot(args, be, dev_id, before))
    payload.update(finish_burst(args))
    payload["elapsed_seconds"] = elapsed_seconds(args)
    payload["summary"] = (f"{len(steps)} steps done" if is_success
                          else f"failed after {completed_count}/{len(steps)} steps"
                               + (f" — step {failed_step} {results[failed_step]['step']}" if failed_step is not None else ""))
    payload["next"] = _next_hint(payload, failed_step)
    return out(payload)


def _cause_of(be, is_success: bool) -> dict:
    """If an Android step failed because the screen tree could not be read, that code (android_system_not_ready etc.)."""
    failure = getattr(be, "device_failure", None)
    return {"cause": failure["code"]} if failure and not is_success else {}


def _next_hint(payload: dict, failed_step: int | None) -> str:
    if payload["ok"]:
        if payload.get("screen_changed") is False:
            return "The screen did not change — look again with app tree"
        return "Read the shot image to check the result" if payload.get("shot") else "app shot  # check the result screen"
    if payload.get("cause"):
        return f"The cause is the device state ({payload['cause']}), not the step — look at the device screen with app shot first"
    if failed_step is None:
        return "Read error (it stopped before reaching a step) — check the device and screen state with app tree"
    return f"Look at the screen with app tree, fix step {failed_step} and run again from that step"


def configure(p) -> None:
    p.add_argument("--steps", default=None,
                   help='run: steps JSON file (e.g. [{"tap": {"text": "Log in"}}, {"wait": {"text": "Home"}}])')
    p.add_argument("--burst", type=burst_spec, default=None,
                   help="tap·swipe·run: capture continuously from before the action until SECONDS after — keeps only changed frames "
                        "(SECONDS[:INTERVAL], e.g. 3 · 5:0.3)")


ACTION = Action(name="run", device_use="mutate", run=_app_run, configure=configure,
                help="Several steps (tap·swipe·type·wait·gone·back) at once — on iOS Maestro starts only once",
                example="app run --device $DEV --steps login.json --shot after_login")
