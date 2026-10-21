"""`app run` — 단계 여러 개를 한 번에 돌린다 (#894).

iOS 는 호출마다 Maestro(JVM)가 새로 떠서 tap 하나에 수십 초다. 단계를 한 flow 로 묶어 Maestro 를 한 번만 띄운다.
Android 는 같은 단계 파일을 기존 백엔드 메서드로 차례로 실행한다 (플랫폼이 달라도 단계 파일은 하나).
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

# Maestro 한 번의 대기: 기동 여유 + 단계당 여유 + wait 단계 시간 합 (초)
MAESTRO_STARTUP_SECONDS = 60
MAESTRO_SECONDS_PER_STEP = 15
# Android wait 의 화면 다시 읽기 간격 (초)
ANDROID_WAIT_POLL_SECONDS = 0.5
# 실패 원인으로 남길 Maestro 출력 줄 수
FAILURE_DETAIL_LINE_COUNT = 6


def _app_run(args) -> int:
    """단계 파일 실행: 검증 > 기기·백엔드 > 입력값 꺼내기 > 실행(iOS 한 flow · Android 차례로) > 결과."""
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
    """이 플랫폼에서 못 하는 단계 > 실행 전에 거절 (중간까지 돌다 멈추지 않게)."""
    for index, step in enumerate(steps):
        if step["kind"] == "back" and not be.has_back_button:
            return {"ok": False, "code": "step_unsupported_on_platform", "step_index": index,
                    "platform": be.name, "error": f"{be.name} has no back button (no back step)",
                    "next": 'Press the on-screen back button with {"tap": {...}} or '
                            '{"swipe": {"from": "0.02,0.5", "to": "0.8,0.5"}} (edge swipe)'}
    return None


def _resolve_secrets(steps: list[dict], be) -> tuple[dict[int, str], dict | None]:
    """type 단계의 값 꺼내기 (환경변수 · 저장된 자격증명) > {단계 번호: 값}. 값은 이 dict 밖으로 나가지 않는다."""
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
    # Maestro 는 inputText 설명에 넣은 값을 그대로 찍는다 — 출력·오류로 나가기 전에 가린다
    for value in secrets.values():
        text = credentials.mask(text, {"password": value})
    return text


# ── iOS: Maestro 한 번 ───────────────────────────────────────────────────

def _run_in_one_flow(be, dev_id: str, steps: list[dict],
                     secrets: dict[int, str]) -> tuple[bool, list[dict], str]:
    """단계 전부 > flow 하나 > Maestro 한 번. 단계별 결과는 Maestro 출력의 '... COMPLETED|FAILED' 줄로 나눈다."""
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
        # 어느 단계에서 멈췄는지 출력에 없다 (기동 실패·시간 초과) — 끝난 단계만 남기고 나머지는 모름
        per_step = [s if s == "completed" else "unknown" for s in per_step]
    results = [{"status": status} for status in per_step]
    if is_success:
        return True, results, ""
    reason = [l for l in lines if "FAILED" in l or "not found" in l.lower() or "Error" in l
              or "Assertion" in l or "did not respond" in l]
    return False, results, "\n".join((reason or lines)[-FAILURE_DETAIL_LINE_COUNT:])


# ── iOS 상주 세션: 단계마다 run 한 번 (#894 2단계) ─────────────────────────

def _run_each_step_in_session(be, dev_id: str, steps: list[dict]) -> tuple[bool, list[dict], str]:
    """세션의 run 은 단계별 상태를 주지 않는다 — 단계마다 따로 불러(호출당 1초 안팎) 어느 단계가 실패했는지 정확히 안다.

    세션이 중간에 끊기면(그 단계는 이미 호출마다 띄우는 길로 돌았다) 나머지는 flow 하나로 몰아 돌린다.
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


# ── Android: 차례로 ──────────────────────────────────────────────────────

def _run_step_by_step(be, dev_id: str, steps: list[dict], secrets: dict[int, str],
                      ime_mode: str = "auto") -> tuple[bool, list[dict], str]:
    """단계를 하나씩 실행. 첫 실패에서 멈추고 나머지는 not_run. 입력기 전환은 첫 type 단계에서 한 번, 끝나면 원복."""
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
            # 단계 자체가 아니라 기기가 원인일 수 있다 (시스템 재시작 중이면 wm size·input 도 실패한다)
            if not be.device_failure:
                be.device_failure = be.system_readiness_failure(dev_id)
            return False, results, detail
    return True, results, ""


def _android_step(be, dev_id: str, step: dict, value: str | None) -> tuple[bool, str, dict]:
    """단계 하나 > (성공 여부, 사유, type 단계의 필드 대조 결과)."""
    if step["kind"] == "type":
        # 단계 파일의 값은 전부 비밀로 다룬다 — 대조 결과에 보이는 글자를 싣지 않는다
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
    """요소가 보일 때까지(gone 이면 사라질 때까지) 화면 구조를 다시 읽는다 (최대 timeout 초)."""
    deadline = time.monotonic() + step["timeout"]
    should_be_gone = step.get("gone", False)
    while True:
        nodes = be.nodes(dev_id) or []
        is_visible = bool(app_input.match_nodes(nodes, step["field"], step["value"]))
        # 화면 구조를 못 읽은 것은 '사라졌다'가 아니다
        if (is_visible and not should_be_gone) or (should_be_gone and nodes and not is_visible):
            return True, ""
        if time.monotonic() >= deadline:
            # 화면 구조를 아예 못 읽은 것이면 '안 보였다'가 아니라 그 원인을 알린다
            if be.device_failure:
                return False, f"{be.device_failure['code']}: {be.device_failure['reason']}"
            if should_be_gone:
                return False, f"{step['field']}={step['value']!r} did not disappear within {step['timeout']}s"
            return False, f"{step['field']}={step['value']!r} did not appear within {step['timeout']}s"
        time.sleep(ANDROID_WAIT_POLL_SECONDS)


# ── 결과 ─────────────────────────────────────────────────────────────────

def _run_result(args, be, dev_id: str, before, steps: list[dict], is_success: bool,
                results: list[dict], detail: str) -> int:
    """단계별 결과 + 전체 결과 > JSON 하나. --shot 은 전부 성공했을 때만 찍는다."""
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
    """Android 단계가 화면 구조를 못 읽어 실패했으면 그 code (android_system_not_ready 등)."""
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
