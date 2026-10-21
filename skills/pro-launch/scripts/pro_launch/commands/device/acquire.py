"""`device acquire` — 조건으로 기기를 빌린다: 판정 > (죽은 세션 설정 되돌림) > (만들기) > (켜기) > 잠금 안에서 확인하고 lease (#953 · #954).

--count N 은 같은 조건으로 서로 다른 기기 N 대 (같은 세션이 쥔 기기는 다음 판정에서 빠진다).
--need 와 함께면 그 상태가 있는 꺼진 기기를 모자란 만큼 먼저 복제한다 (iOS — 복제본의 상태는 확인 전으로 표시).
"""
from __future__ import annotations

import hashlib
import time

from pro_launch.commands.device.claims import run_restore_commands
from pro_launch.runtime import (android_device, boot_turn, device_backends, device_benchmark, device_claims, device_marks,
                                device_pool_facts)
from pro_launch.runtime.context import project_root
from pro_launch.runtime.device_backends.base import default_device_name
from pro_launch.runtime.device_boot import resolve_window
from pro_launch.runtime.device_pool import AcquireRequest, Candidate, decide
from pro_launch.runtime.host_resources import MEMORY_RISK_NEXT
from pro_launch.runtime.output import out
from pro_launch.runtime.session_identity import session_identity

# acquire --wait 한 번의 최대 대기 (초) — agent 도구의 명령 시간 상한(기본 2분) 안
ACQUIRE_WAIT_MAXIMUM_SECONDS = 90
ACQUIRE_POLL_SECONDS = 15
# 경합으로 고른 기기를 놓쳤을 때 다시 판정하는 횟수
CLAIM_RACE_RETRIES = 3
# --count 상한 (한 번에 빌리는 기기 수)
ACQUIRE_COUNT_MAXIMUM = 4


def wait_key(request: AcquireRequest) -> str:
    """대기 기록 키: 세션 + 조건 (같은 조건을 다시 부르면 대기 시간이 이어진다)."""
    condition = (f"{request.platform}|{request.form}|{request.os_minimum}|{request.device}|"
                 f"{','.join(request.needs)}|{request.is_fresh_required}")
    return f"{session_identity()}|{hashlib.sha1(condition.encode('utf-8')).hexdigest()[:10]}"


def _restore_dead_session_settings(key: str, dead_lease: dict) -> list[dict]:
    """reclaim: 죽은 세션이 바꾼 설정을 되돌린다 > 실패 목록 (실패한 것은 이 세션 기록으로 남긴다)."""
    settings = device_claims.pop_settings_of_session(key, dead_lease.get("session"))
    failed = [setting for setting in settings if not run_restore_commands(setting)["is_ok"]]
    if failed:
        device_claims.keep_settings_for_this_session(key, failed)
    return [{"key": setting.get("key"), "restore_commands": setting.get("restore_commands")} for setting in failed]


def _failure(code: str, verdict: str, device: str | None, detail: str | None, reasons, next_step: str) -> dict:
    return {"ok": False, "code": code, "verdict": verdict, "device": device, "error": detail,
            "reasons": list(reasons), **android_device.host_pressure_fields(), "next": next_step}


def _create_device(request: AcquireRequest, args) -> tuple[dict | None, Candidate | None]:
    """임시 기기를 만들고 원장에 기록 > (실패 응답, 꺼진 새 기기 후보)."""
    backend = next(b for b in device_backends.backends_for(request.platform) if b.capabilities.can_create)
    name = getattr(args, "name", None) or default_device_name(time.strftime("%Y%m%d-%H%M%S"))
    created = backend.create(name, request.form, request.os_minimum)
    if not created["is_ok"]:
        return _failure("create_failed", "create", None, created["detail"], [],
                        "devices 로 기존 기기를 보고 조건을 넓히거나, 도구(Xcode 런타임 · Android SDK)를 확인한다"), None
    reason = getattr(args, "reason", None) or request.purpose or "acquire: 조건에 맞는 빈 기기 없음"
    device_marks.record_created(created["key"], reason, device_marks.temporary_ttl_days(), backend.name)
    facts = next((f for f in backend.list_devices() if f.key == created["key"]), None)
    if facts is None:
        return _failure("create_failed", "create", created["key"], "만든 기기가 목록에 보이지 않는다", [],
                        "devices 로 확인한다"), None
    return None, Candidate(facts, backend.capabilities)


def _take(decision, candidate: Candidate, request: AcquireRequest, args) -> tuple[dict | None, dict | None]:
    """고른 기기를 켜고 쥔다 > (실패 응답, 결과). 경합으로 남이 먼저 쥐었으면 (None, None)."""
    backend = device_backends.backend_named(candidate.facts.backend)
    unrestored = (_restore_dead_session_settings(candidate.facts.key, decision.reclaimed_from)
                  if decision.reclaimed_from else [])
    instance, is_booted_now = candidate.facts.instance, False
    if decision.is_boot_needed and not candidate.facts.is_booted:
        window, scale = resolve_window(getattr(args, "window", None), getattr(args, "scale", None))
        booted = backend.boot(candidate.facts.key, window, scale)
        if not booted["is_ok"]:
            return _failure("boot_failed", decision.verdict, candidate.facts.key, booted.get("detail"), decision.reasons,
                            "device list 로 상태를 본다. 메모리 압박이면 다른 기기를 끄기 전에 사용자에게 묻는다"), None
        instance, is_booted_now = booted["instance"], not booted.get("already_booted")
    claimed = device_claims.claim_device(instance or candidate.facts.key, str(project_root(args)),
                                         purpose=request.purpose, is_booted_by_lease=is_booted_now,
                                         backend=backend.name, is_free_required=request.device is None)
    if claimed is None:
        return None, None
    if is_booted_now:
        device_claims.set_pool_booted(instance or candidate.facts.key, True)
    # 누가 한 번 쓴 기기는 더 이상 새 폰이 아니다
    device_marks.clear_pristine(candidate.facts.key)
    return None, {"candidate": candidate, "instance": instance, "booted": is_booted_now, "lease": claimed["lease"],
                  "unrestored_settings": unrestored}


def _decide_with_wait(request: AcquireRequest, wait_seconds: float):
    """판정 > wait 이면 상한까지 폴링하며 다시 판정. > (decision, candidates, waited_total_seconds)"""
    key = wait_key(request)
    deadline = time.monotonic() + min(max(wait_seconds, 0), ACQUIRE_WAIT_MAXIMUM_SECONDS)
    while True:
        candidates = device_pool_facts.build_candidates(request.platform)
        context = device_pool_facts.build_context(request.platform, device_claims.waited_seconds(key))
        decision = decide(request, candidates, context)
        if decision.verdict != "wait" or time.monotonic() + ACQUIRE_POLL_SECONDS > deadline:
            break
        device_claims.record_wait(key)
        time.sleep(ACQUIRE_POLL_SECONDS)
    waited_total = device_claims.record_wait(key) if decision.verdict == "wait" else context.waited_seconds
    return decision, candidates, waited_total


def identity_next(next_step: str) -> str:
    if device_claims.owner_identity_strength() == "weak":
        return f"LAUNCH_SESSION 환경변수로 세션 이름을 정한다 (지금은 다른 세션과 구분되지 않는다) · {next_step}"
    return next_step


def acquire_once(request: AcquireRequest, args) -> dict:
    """한 대 빌리기 > 응답 dict (출력하지 않는다). 켜야 하면 켜기 차례를 얻은 뒤 최신 상태로 다시 판정한다."""
    decision, _, _ = _decide_with_wait(request, getattr(args, "wait", 0) or 0)
    if decision.verdict in ("reuse", "reclaim", "create") and decision.is_boot_needed:
        try:
            with boot_turn.boot_turn():
                return _acquire_attempts(request, args, wait_seconds=0)
        except boot_turn.BootTurnBusyError:
            return {"ok": False, "code": "device_busy", "verdict": "wait",
                    "reasons": ["다른 세션이 기기를 켜는 중이다 — 한 번에 하나씩 켠다"],
                    "next": identity_next("잠시 뒤 device acquire 를 다시 부른다")}
    return _acquire_attempts(request, args, wait_seconds=getattr(args, "wait", 0) or 0)


def _acquire_attempts(request: AcquireRequest, args, wait_seconds: float) -> dict:
    for _ in range(CLAIM_RACE_RETRIES):
        decision, candidates, waited_total = _decide_with_wait(request, wait_seconds)
        base = {"verdict": decision.verdict, "reasons": list(decision.reasons), "limits": device_pool_facts.limits_view(),
                "owner_identity": device_claims.owner_identity_strength()}
        if decision.verdict in ("reuse", "reclaim", "create"):
            if decision.verdict == "create":
                failure, candidate = _create_device(request, args)
            else:
                failure, candidate = None, next(c for c in candidates if c.facts.key == decision.device_key)
            if failure is None:
                failure, taken = _take(decision, candidate, request, args)
            if failure is not None:
                return {**base, **failure}
            if taken is None:
                continue   # 잠금 안에서 보니 남이 먼저 쥐었다 — 다시 판정
            device_claims.clear_wait(wait_key(request))
            facts = taken["candidate"].facts
            dev_id = taken["instance"] or facts.key
            return {**base, "action": "acquire", "platform": facts.platform, "device": dev_id, "key": facts.key,
                    "name": facts.name, "lease_id": taken["lease"]["lease_id"], "booted": taken["booted"],
                    "created": decision.verdict == "create", "unrestored_settings": taken["unrestored_settings"],
                    "summary": f"{facts.name} ({dev_id}) 를 빌렸다" + (" — 새로 만들었다" if decision.verdict == "create"
                                                                       else " — 켰다" if taken["booted"] else ""),
                    "next": identity_next(f"DEV={dev_id} 로 작업 > 끝나면 device release --device {dev_id}")}
        if decision.verdict == "wait":
            return {"ok": False, "code": "device_busy", **base, "waited_total_seconds": round(waited_total),
                    "owners": list(decision.busy_owners),
                    "next": identity_next("device acquire 를 --wait 90 으로 다시 부르거나 다른 일을 먼저 한다")}
        if decision.verdict == "ask":
            # 메모리 위험이면 --user-approved 로만 넘는다 (--yes 는 넘지 않는다, #972)
            return {"ok": False, "code": "needs_user", **base, "owners": list(decision.busy_owners),
                    "is_memory_risk": decision.is_memory_risk, **android_device.host_pressure_fields(),
                    # 메모리 때문에 멈췄으면 기기 밖 큰 소비자를 함께 보여 준다 (#964)
                    "non_device_consumers": device_benchmark.non_device_consumers(),
                    "next": (MEMORY_RISK_NEXT if decision.is_memory_risk
                             else "reasons 를 사용자에게 그대로 보여 주고 어떻게 할지 묻는다")}
        next_step = ("그 상태를 사람이 기기에 만든 뒤 device mark 로 기록한다" if request.needs
                     else "devices 로 목록을 확인하고 조건(--form · --os · --device)을 넓힌다")
        return {"ok": False, "code": "no_matching_device", **base, "next": next_step}
    return {"ok": False, "code": "device_busy", "verdict": "wait", "reasons": ["고른 기기를 다른 세션이 연달아 먼저 쥐었다"],
            "next": "잠시 뒤 다시 device acquire"}


def _clone_for_count(request: AcquireRequest, count: int, args) -> list[dict]:
    """--count N --need: 그 상태가 있는 빈 기기가 N 대보다 적으면, 꺼진 원본을 모자란 만큼 복제한다 > 복제 결과 목록.

    원본이 켜져 있으면 복제할 수 없다(simctl 제약) — 그때는 복제하지 않고 acquire 가 wait 를 낸다.
    """
    from pro_launch.commands.device.lifecycle import clone_device
    candidates = device_pool_facts.build_candidates(request.platform)
    free = [c for c in candidates if all(need in c.marks for need in request.needs)
            and not c.live_other_leases and not c.own_leases]
    source = next((c for c in free if not c.facts.is_booted and c.capabilities.can_clone
                   and c.capabilities.can_clone_keep_marks), None)
    if source is None or len(free) >= count:
        return []
    backend = device_backends.backend_named(source.facts.backend)
    reason = getattr(args, "reason", None) or f"acquire --count {count} --need {','.join(request.needs)}"
    return [clone_device(source.facts, backend, None, reason, None) for _ in range(count - len(free))]


def run_acquire(args) -> int:
    if args.platform not in ("ios", "android"):
        return out({"ok": False, "code": "args_required", "error": "--platform ios 또는 android 가 필요하다",
                    "next": "device acquire --platform ios --purpose '#이슈'"})
    # --reason 은 --purpose 의 별칭 (create 와 헷갈려 쓴다, #972)
    request = AcquireRequest(platform=args.platform, form=args.form or "phone", os_minimum=args.os,
                             device=args.device, purpose=args.purpose or getattr(args, "reason", None),
                             needs=tuple(getattr(args, "need", None) or ()),
                             is_fresh_required=bool(getattr(args, "fresh", False)),
                             is_memory_risk_user_approved=bool(getattr(args, "user_approved", False)))
    count = max(1, min(int(getattr(args, "count", 1) or 1), ACQUIRE_COUNT_MAXIMUM))
    if count == 1:
        return out(acquire_once(request, args))
    clones = _clone_for_count(request, count, args) if request.needs else []
    results = []
    for _ in range(count):
        results.append(acquire_once(request, args))
        if results[-1].get("ok") is False:
            break
    is_all_taken = len(results) == count and all(r.get("ok") is not False for r in results)
    return out({"ok": is_all_taken, "code": "ok" if is_all_taken else "partial", "action": "acquire", "count": count,
                "devices": [r.get("device") for r in results if r.get("ok") is not False], "results": results,
                "clones": clones,
                "summary": f"{sum(r.get('ok') is not False for r in results)}/{count} 대 빌림",
                "next": "빌린 기기마다 끝나면 device release (또는 device release --all)"
                        if is_all_taken else "빌린 것은 쓰거나 release 하고, 실패 결과의 next 를 본다"})
