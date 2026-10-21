"""app 의 탭·스와이프가 함께 쓰는 것 — 백엔드 고르기 · 조작 전후 화면 비교 · 결과 응답."""
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

# Maestro iOS 드라이버 기동 대기 환경변수 · 과부하일 때 값 (밀리초) — 사용자가 정한 값은 그대로 (#922)
DRIVER_STARTUP_TIMEOUT_ENV = "MAESTRO_DRIVER_STARTUP_TIMEOUT"
OVERLOADED_DRIVER_STARTUP_TIMEOUT_MILLISECONDS = 180000
# 실패 응답에 호스트 상태를 붙이는 메모리 압박 단계
REPORTED_MEMORY_PRESSURES = ("high", "critical")
# 상주 세션 없이 iOS 조작이 이보다 오래 걸리면 세션을 권한다 (초, 세션이면 1초 안팎)
SLOW_IOS_WITHOUT_SESSION_SECONDS = 15
# 세션이 아예 없다는 뜻의 session_fallback (그 밖의 사유는 세션이 있으나 못 쓴 것 — 다시 켜라고 하지 않는다)
SESSION_MISSING_FALLBACKS = ("session_gone",)


def elapsed_seconds(args) -> float | None:
    """`app` 호출 시작부터 지금까지 (초). 시작 표시가 없으면(동작을 직접 부른 테스트) None."""
    started = getattr(args, "started_monotonic", None)
    return round(time.monotonic() - started, 1) if started is not None else None


def backend_for(args):
    """(백엔드, 기기 id, 오류 응답). 기기를 못 고르거나 도구가 없으면 오류 응답을 채운다."""
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return None, None, no_device_response(dev, args.device)
    be, err = backend_on(platform, args, dev_id)
    return be, (dev_id if be else None), err


def backend_on(platform: str, args, dev_id: str | None = None):
    """(백엔드, 오류 응답) — 기기를 이미 고른 동작용. 백엔드가 없거나 도구가 없으면 오류 응답을 채운다."""
    be = app_input.get_backend(platform, getattr(args, "pkg", None) or os.environ.get("PKG"))
    if be is None:
        return None, out({"ok": False, "code": "platform_unsupported",
                          "error": f"{platform} 은 조작 백엔드가 없다",
                          "next": "references/extending.md 를 보고 백엔드를 추가한다"})
    if not be.available():
        return None, out({"ok": False, "code": f"{be.name}_tool_missing",
                          "error": f"{be.name} 조작 도구가 없다", "next": be.install_hint})
    if be.name == "ios":
        prepare_ios_maestro(dev_id)
    return be, None


def prepare_ios_maestro(dev_id: str | None) -> None:
    """iOS 조작 전: 같은 기기의 고아 드라이버 정리 > 과부하면 드라이버 기동 대기 늘리기 (자식 maestro·중계가 물려받는다)."""
    try:
        maestro_drivers.clean_auto(dev_id)
    except Exception:   # noqa: BLE001 — 정리는 보조다, 조작을 막지 않는다
        pass
    if DRIVER_STARTUP_TIMEOUT_ENV not in os.environ and host_resources.read_load()["is_overloaded"]:
        os.environ[DRIVER_STARTUP_TIMEOUT_ENV] = str(OVERLOADED_DRIVER_STARTUP_TIMEOUT_MILLISECONDS)


def session_fields(be) -> dict:
    """iOS 상주 세션을 탔는지 · 못 써서 내려갔는지 · Maestro 잠금 대기 · 자동 정리한 고아 드라이버 (없으면 키 없음)."""
    fields = dict(getattr(be, "session_report", None) or {})
    if getattr(be, "name", None) == "ios":
        fields.update(maestro_runs.lock_wait_report())
        if maestro_drivers.CLEANED_DRIVERS:
            fields["cleaned_stale_drivers"] = list(maestro_drivers.CLEANED_DRIVERS)
    return fields


def with_session_advice(result: dict, be, dev_id: str | None, args) -> dict:
    """iOS 이고 상주 세션 없이 15초를 넘겼으면 next 를 app session start 로 바꾸고 원래 next 는 hint 로 옮긴다."""
    if getattr(be, "name", None) != "ios":
        return result
    report = getattr(be, "session_report", None) or {}
    has_no_session = not report or report.get("session_fallback") in SESSION_MISSING_FALLBACKS
    elapsed = elapsed_seconds(args)
    if not has_no_session or elapsed is None or elapsed <= SLOW_IOS_WITHOUT_SESSION_SECONDS:
        return result
    previous_next = result.get("next")
    result["next"] = (f"app session start --device {dev_id}  "
                      f"# 이번 {elapsed}초 — 세션이면 tap 1초 · tree 0.6초 (조작을 더 할 때)")
    result["hint"] = ("상주 세션 없이 iOS 조작은 호출마다 Maestro(JVM)를 새로 띄운다"
                      + (f" — 세션을 켠 뒤: {previous_next}" if previous_next else ""))
    return result


def ios_failure_fields(be, dev_id: str | None) -> dict:
    """iOS Maestro 실패에 붙일 진단 4개: 남은 고아 드라이버 · 지금 도는 다른 Maestro · 호스트 부하 · Maestro 마지막 오류 줄."""
    if getattr(be, "name", None) != "ios":
        return {}
    fields: dict = {}
    try:
        fields.update(maestro_drivers.failure_fields(dev_id))
    except Exception:   # noqa: BLE001 — 진단이 실패 응답을 망치면 안 된다
        pass
    fields.update(host_load_fields())
    last_error = maestro_runs.last_error_line()
    if last_error:
        fields["backend_last_error"] = last_error
    return fields


def host_load_fields() -> dict:
    """부하가 코어 수 2배를 넘거나 메모리 압박이 high 이상이면 {host_load: ...}, 아니면 {}."""
    load = host_resources.read_load()
    memory_pressure = host_resources.memory_summary()["pressure"]
    if not load["is_overloaded"] and memory_pressure not in REPORTED_MEMORY_PRESSURES:
        return {}
    return {"host_load": {"load_1m": load["load_1m"], "load_5m": load["load_5m"], "cpu_count": load["cpu_count"],
                          "is_overloaded": load["is_overloaded"], "memory_pressure": memory_pressure,
                          "driver_startup_timeout_ms": os.environ.get(DRIVER_STARTUP_TIMEOUT_ENV)}}


def device_failure_response(be, dev_id, args=None) -> int:
    """화면 구조를 못 읽었다 — 원인별 code (시스템 재시작 중 · UiAutomation 연결 실패 · 시간 초과 · 그 밖)."""
    failure = getattr(be, "device_failure", None) or {"code": "ui_dump_failed", "reason": None}
    next_hint = {
        "android_system_not_ready": "app shot 으로 화면을 본다. 부팅 화면이 계속되면 에뮬레이터를 다시 켠다 (cold boot — 사용자에게 먼저 묻는다)",
        "ui_automation_unavailable": "다른 자동화 도구(Maestro·Appium)가 기기를 쓰는 중인지 본다. 잠시 뒤 다시 시도하거나 --at 비율 좌표를 쓴다",
        "ui_dump_timeout": "애니메이션이 계속되는 화면일 수 있다. app shot 으로 보고 --at 비율 좌표를 쓴다",
    }.get(failure["code"], "잠시 뒤 다시 시도하거나 --at 비율 좌표를 쓴다")
    return out({"ok": False, "code": failure["code"], "device": dev_id,
                "error": failure.get("reason") or "화면 구조를 읽지 못했다 (애니메이션 중이거나 보안 화면일 수 있다)",
                "elapsed_seconds": elapsed_seconds(args) if args is not None else None,
                "next": next_hint})


def before_shot(args, be, dev_id) -> bytes | None:
    """--shot 일 때만 동작 전 화면을 기억한다 — 나중에 '바뀐 뒤 멈춘 화면'을 고르는 기준. --burst 면 연속 캡처도 여기서 시작."""
    start_burst(args, be, dev_id)
    return be.grab(dev_id) if getattr(args, "shot", None) else None


def after_shot(args, be, dev_id, before: bytes | None) -> dict:
    """--shot 이면 동작 결과 화면을 찍는다 — 확인용 shot 호출 한 번을 아낀다.

    고정 대기는 실패한다(실측): Android 는 캡처가 느려 전환이 시작되기도 전에 같은 장면을 두 번
    찍고 '멈췄다'고 판단했다. 그래서 **동작 전 화면과 달라진 뒤, 연속 두 장이 같아질 때**를 고른다.
    끝내 안 바뀌면 screen_changed=false — '눌렀는데 반응 없음'을 agent 가 바로 안다.
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
    # 백엔드가 사유를 비워 두면 Maestro 마지막 오류 줄 > 그것도 없으면 사유 없음을 그대로 (error: null 금지)
    error = None if ok else ((detail or "")[-400:] or diagnostics.get("backend_last_error")
                             or f"{be.name} 백엔드가 사유를 남기지 않고 실패했다")
    res = {"ok": ok, "code": "ok" if ok else fail_code, "device": dev_id, "via": be.name,
           **session_fields(be), **extra, "error": error, **diagnostics,
           "summary": summary if ok else f"실패 — {fail_code}",
           "next": "app shot  # 결과 화면 확인"}
    if diagnostics.get("stale_maestro_drivers"):
        res["next"] = f"app session stop --device {dev_id} --kill-stale  # 남은 Maestro 드라이버 정리 후 다시"
    if ok:
        auto_record_backend(be)
        res.update(after_shot(args, be, dev_id, before))
    res.update(finish_burst(args))
    # 조작 비용을 보이게 한다 — iOS 는 호출마다 Maestro(JVM)가 새로 떠서 수십 초다 (#894)
    res["elapsed_seconds"] = elapsed_seconds(args)
    if ok:
        if res.get("shot"):
            res["next"] = ("shot 이미지를 읽어 결과를 확인한다" if res.get("screen_changed") is not False
                           else "화면이 그대로다 — 다른 요소를 고르거나 app tree 로 다시 본다")
    # 남은 Maestro 드라이버 정리 안내가 우선 — 세션을 켜도 안 풀린다
    if not diagnostics.get("stale_maestro_drivers"):
        with_session_advice(res, be, dev_id, args)
    return out(res)


_BACKEND_HOW = {"android": "앱 누르기·밀기는 launch_cli app tap/swipe (uiautomator + adb input, 화면 요소 기준)로 된다",
                "ios": "앱 누르기·밀기는 launch_cli app tap/swipe (Maestro, 화면 요소 기준)로 된다"}


def auto_record_backend(be) -> None:
    """실제로 성공한 조작 방식을 이 컴퓨터 범위에 남긴다 — 검증된 것만, 하루 한 번."""
    how = _BACKEND_HOW.get(be.name)
    if how:
        try:
            knowledge.auto_record(be.name, f"{be.name}.input", how)
        except Exception:   # noqa: BLE001 — 기록 실패가 조작 결과를 바꾸면 안 된다
            pass


def not_found_response(be, dev_id, field: str, value: str, nodes: list[dict] | None, args=None) -> int:
    """못 찾았을 때 추측을 반복하지 않도록 화면 언어 · 화면에 실제로 있는 값(문구는 text·desc 둘 다) · 가장 비슷한 선택자."""
    if nodes is None:
        nodes = be.nodes(dev_id) or []
    suggestion = node_match.did_you_mean(nodes, value)
    return out(with_session_advice({"ok": False, "code": "not_found", "device": dev_id,
                "error": f"{field}={value!r} 인 요소가 없다 (text·desc 모두, 겹친 라벨·부분 일치 포함)",
                "locale": be.locale(dev_id), "candidates": node_match.candidate_values(nodes, field),
                **({"did_you_mean": suggestion} if suggestion else {}), **session_fields(be),
                "elapsed_seconds": elapsed_seconds(args),
                "next": "candidates 의 값으로 다시 app tap (문구는 화면 언어 그대로)"}, be, dev_id, args))
