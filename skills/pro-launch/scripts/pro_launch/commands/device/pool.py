"""`device acquire` · `device release` · `device shutdown` — 조건으로 빌리고, 반납하며 켠 것을 끈다 (#953).

acquire: 판정(device_pool.decide) > (reclaim 이면 죽은 세션 설정 되돌림) > (꺼져 있으면 켬) > 잠금 안에서 다시 확인하고 lease.
release: 설정 되돌림 > lease 삭제 > 이 빌림이 켰고 남은 소유가 없으면 끔.
"""
from __future__ import annotations

import hashlib
import time

from pro_launch.commands.device.claims import refuse_other_session_owner, resolve_device, run_restore_commands
from pro_launch.runtime import device_backends, device_claims, device_ledger, host_resources
from pro_launch.runtime.context import project_root
from pro_launch.runtime.device_boot import resolve_window
from pro_launch.runtime.device_pool import AcquireRequest, Candidate, PoolContext, decide
from pro_launch.runtime.output import out
from pro_launch.runtime.session_identity import session_identity

# acquire --wait 한 번의 최대 대기 (초) — agent 도구의 명령 시간 상한(기본 2분) 안
ACQUIRE_WAIT_MAXIMUM_SECONDS = 90
ACQUIRE_POLL_SECONDS = 15
# 합친 대기 한도 기본값 (분) — launch.devices.wait_limit_minutes 로 덮어쓴다
WAIT_LIMIT_DEFAULT_MINUTES = 10
# 경합으로 고른 기기를 놓쳤을 때 다시 판정하는 횟수
CLAIM_RACE_RETRIES = 3


def _devices_config() -> dict:
    return (device_claims.common_config.get_section("launch") or {}).get("devices") or {}


def _limits() -> dict:
    """판정에 쓴 한도와 출처 (응답 limits 필드)."""
    config = _devices_config()
    wait_minutes = config.get("wait_limit_minutes")
    idle_minutes = config.get("lease_idle_minutes")
    return {"wait_limit_minutes": {"value": wait_minutes if wait_minutes else WAIT_LIMIT_DEFAULT_MINUTES,
                                   "source": "config" if wait_minutes else "default"},
            "lease_idle_minutes": {"value": device_claims.lease_idle_seconds() / 60,
                                   "source": "config" if idle_minutes else "default"}}


def _wait_key(request: AcquireRequest) -> str:
    """대기 기록 키: 세션 + 조건 (같은 조건을 다시 부르면 대기 시간이 이어진다)."""
    condition = f"{request.platform}|{request.form}|{request.os_minimum}|{request.device}"
    return f"{session_identity()}|{hashlib.sha1(condition.encode('utf-8')).hexdigest()[:10]}"


def build_candidates(platform: str) -> list[Candidate]:
    """기기 사실 + 원장 > 판정 재료. 호스트 생존은 pid 마다 한 번만 본다."""
    ledger, now, probe = device_ledger.read_ledger(), time.time(), device_claims._HostProbe()
    candidates = []
    for backend in device_backends.backends_for(platform):
        for facts in backend.list_devices():
            entry = ledger["devices"].get(facts.key) or {"leases": []}
            own, live_other, dead_other = [], [], []
            for lease in entry["leases"]:
                if device_claims.is_own_lease(lease):
                    own.append(lease)
                elif device_claims.is_lease_live(lease, now, probe):
                    live_other.append(lease)
                else:
                    dead_other.append(lease)
            last_used = max((lease.get("last_used") or 0 for lease in entry["leases"]), default=None)
            candidates.append(Candidate(facts, backend.capabilities, tuple(live_other), tuple(dead_other), tuple(own),
                                        is_pool_booted=bool(entry.get("pool_booted_at")) and facts.is_booted,
                                        last_used=last_used))
    return candidates


def _restore_dead_session_settings(key: str, dead_lease: dict) -> list[dict]:
    """reclaim: 죽은 세션이 바꾼 설정을 되돌린다 > 실패 목록 (실패한 것은 이 세션 기록으로 남긴다)."""
    settings = device_claims.pop_settings_of_session(key, dead_lease.get("session"))
    failed = [setting for setting in settings if not run_restore_commands(setting)["is_ok"]]
    if failed:
        device_claims.keep_settings_for_this_session(key, failed)
    return [{"key": setting.get("key"), "restore_commands": setting.get("restore_commands")} for setting in failed]


def _take(decision, candidates: list[Candidate], request: AcquireRequest, args) -> tuple[int | None, dict | None]:
    """고른 기기를 켜고 쥔다 > (실패 응답, 결과). 경합으로 남이 먼저 쥐었으면 (None, None)."""
    candidate = next(c for c in candidates if c.facts.key == decision.device_key)
    backend = device_backends.backend_named(candidate.facts.backend)
    unrestored = (_restore_dead_session_settings(candidate.facts.key, decision.reclaimed_from)
                  if decision.reclaimed_from else [])
    instance, is_booted_now = candidate.facts.instance, False
    if decision.needs_boot:
        window, scale = resolve_window(getattr(args, "window", None), getattr(args, "scale", None))
        booted = backend.boot(candidate.facts.key, window, scale)
        if not booted["is_ok"]:
            return out({"ok": False, "code": "boot_failed", "verdict": decision.verdict, "device": candidate.facts.key,
                        "error": booted.get("detail"), "reasons": list(decision.reasons),
                        **host_resources_fields(),
                        "next": "device list 로 상태를 본다. 메모리 압박이면 다른 기기를 끄기 전에 사용자에게 묻는다"}), None
        instance, is_booted_now = booted["instance"], not booted.get("already_booted")
    claimed = device_claims.claim_device(instance or candidate.facts.key, str(project_root(args)),
                                         purpose=request.purpose, booted_by_lease=is_booted_now,
                                         backend=backend.name, is_free_required=request.device is None)
    if claimed is None:
        return None, None
    if is_booted_now:
        device_claims.set_pool_booted(instance or candidate.facts.key, True)
    return None, {"candidate": candidate, "instance": instance, "booted": is_booted_now, "lease": claimed["lease"],
                  "unrestored_settings": unrestored}


def host_resources_fields() -> dict:
    return {"resources": host_resources.memory_summary()}


def _decide_with_wait(request: AcquireRequest, wait_seconds: float):
    """판정 > wait 이면 상한까지 폴링하며 다시 판정. > (decision, candidates, waited_total_seconds)"""
    wait_key = _wait_key(request)
    wait_limit_seconds = float(_limits()["wait_limit_minutes"]["value"]) * 60
    deadline = time.monotonic() + min(max(wait_seconds, 0), ACQUIRE_WAIT_MAXIMUM_SECONDS)
    while True:
        candidates = build_candidates(request.platform)
        pressure = host_resources.memory_summary().get("pressure") or "unknown"
        context = PoolContext(pressure=pressure, waited_seconds=device_claims.waited_seconds(wait_key),
                              wait_limit_seconds=wait_limit_seconds)
        decision = decide(request, candidates, context)
        if decision.verdict != "wait" or time.monotonic() + ACQUIRE_POLL_SECONDS > deadline:
            break
        device_claims.record_wait(wait_key)
        time.sleep(ACQUIRE_POLL_SECONDS)
    waited_total = device_claims.record_wait(wait_key) if decision.verdict == "wait" else context.waited_seconds
    return decision, candidates, waited_total


def _identity_next(next_step: str) -> str:
    if device_claims.owner_identity_strength() == "weak":
        return f"LAUNCH_SESSION 환경변수로 세션 이름을 정한다 (지금은 다른 세션과 구분되지 않는다) · {next_step}"
    return next_step


def run_acquire(args) -> int:
    if args.platform not in ("ios", "android"):
        return out({"ok": False, "code": "args_required", "error": "--platform ios 또는 android 가 필요하다",
                    "next": "device acquire --platform ios --purpose '#이슈'"})
    request = AcquireRequest(platform=args.platform, form=args.form or "phone", os_minimum=args.os,
                             device=args.device, purpose=args.purpose)
    for _ in range(CLAIM_RACE_RETRIES):
        decision, candidates, waited_total = _decide_with_wait(request, args.wait or 0)
        base = {"verdict": decision.verdict, "reasons": list(decision.reasons), "limits": _limits(),
                "owner_identity": device_claims.owner_identity_strength()}
        if decision.verdict in ("reuse", "reclaim"):
            failure, taken = _take(decision, candidates, request, args)
            if failure is not None:
                return failure
            if taken is None:
                continue   # 잠금 안에서 보니 남이 먼저 쥐었다 — 다시 판정
            device_claims.clear_wait(_wait_key(request))
            facts = taken["candidate"].facts
            dev_id = taken["instance"] or facts.key
            return out({**base, "action": "acquire", "platform": facts.platform, "device": dev_id, "key": facts.key,
                        "name": facts.name, "lease_id": taken["lease"]["lease_id"], "booted": taken["booted"],
                        "unrestored_settings": taken["unrestored_settings"],
                        "summary": f"{facts.name} ({dev_id}) 를 빌렸다" + (" — 켰다" if taken["booted"] else ""),
                        "next": _identity_next(f"DEV={dev_id} 로 작업 > 끝나면 device release --device {dev_id}")})
        if decision.verdict == "wait":
            return out({"ok": False, "code": "device_busy", **base, "waited_total_seconds": round(waited_total),
                        "owners": list(decision.busy_owners),
                        "next": _identity_next("device acquire 를 --wait 90 으로 다시 부르거나 다른 일을 먼저 한다")})
        if decision.verdict == "ask":
            return out({"ok": False, "code": "needs_user", **base, "owners": list(decision.busy_owners),
                        **host_resources_fields(), "next": "reasons 를 사용자에게 그대로 보여 주고 어떻게 할지 묻는다"})
        return out({"ok": False, "code": "no_matching_device", **base,
                    "next": "devices 로 목록을 확인하고 조건(--form · --os · --device)을 넓힌다"})
    return out({"ok": False, "code": "device_busy", "verdict": "wait", "reasons": ["고른 기기를 다른 세션이 연달아 먼저 쥐었다"],
                "next": "잠시 뒤 다시 device acquire"})


def _release_one(dev_id: str, lease_id: str | None, is_keep_booted: bool) -> dict:
    """lease 하나 반납 > 결과 행 {device, released, restored, shutdown, shutdown_reason}."""
    released = device_claims.release_device(dev_id, lease_id)
    if released is None:
        return {"device": dev_id, "released": False, "restored": [], "shutdown": False, "shutdown_reason": "no_lease"}
    restored = [run_restore_commands(setting) for setting in released["settings"]]
    lease, key = released["lease"], released["owner"]["key"]
    entry = device_ledger.read_ledger()["devices"].get(key) or {}
    is_pool_booted = bool(lease.get("booted_by_lease") or entry.get("pool_booted_at"))
    reason = ("keep_booted" if is_keep_booted else "another_lease" if released["remaining_live_leases"]
              else "not_booted_by_lease" if not is_pool_booted or not lease.get("backend") else None)
    is_shut = False
    if reason is None:
        result = device_backends.backend_named(lease["backend"]).shutdown(key, lease.get("instance"))
        is_shut, reason = result["is_ok"], None if result["is_ok"] else f"shutdown_failed: {result['detail']}"
        if is_shut:
            device_claims.set_pool_booted(key, False)
    return {"device": dev_id, "key": key, "released": True, "restored": restored, "shutdown": is_shut,
            "shutdown_reason": reason}


def run_release(args) -> int:
    if getattr(args, "all", False):
        rows = [_release_one(lease.get("instance") or key, lease.get("lease_id"), args.keep_booted)
                for key, lease in device_claims.leases_of_session(session_identity())]
        failed = [r for row in rows for r in row["restored"] if not r["is_ok"]]
        return out({"ok": not failed, "code": "restore_failed" if failed else "ok", "action": "release", "all": True,
                    "released": rows, "summary": f"이 세션 lease {len(rows)}개 반납 · 끈 기기 {sum(r['shutdown'] for r in rows)}",
                    "next": "되돌리지 못한 설정은 failed_command 를 직접 실행한다" if failed else None})
    platform, dev_id, err = resolve_device(args)
    if err is not None:
        return err
    existing = device_claims.device_owner(dev_id)
    if existing is None:
        return out({"action": "release", "platform": platform, "device": dev_id, "released": False,
                    "summary": "쥔 기록이 없다", "next": None})
    if existing["is_live"] and existing["session"] != session_identity() and not args.yes:
        return refuse_other_session_owner(dev_id, "release")
    row = _release_one(dev_id, getattr(args, "lease", None), args.keep_booted)
    failed = [r for r in row["restored"] if not r["is_ok"]]
    return out({"ok": not failed, "code": "restore_failed" if failed else "ok", "action": "release",
                "platform": platform, **row,
                "summary": f"{dev_id} 반납 · 되돌린 설정 {len(row['restored']) - len(failed)}/{len(row['restored'])}"
                           + (" · 껐다" if row["shutdown"] else ""),
                "error": failed[0]["detail"] if failed else None,
                "next": "되돌리지 못한 설정은 failed_command 를 직접 실행한다" if failed else None})


def run_shutdown(args) -> int:
    platform, dev_id, err = resolve_device(args)
    if err is not None:
        return err
    if not args.yes and (refusal := refuse_other_session_owner(dev_id, "shutdown")) is not None:
        return refusal
    key = device_claims.resolve_instance_key(dev_id)
    facts = next((f for f in device_backends.all_device_facts(platform) if dev_id in (f.key, f.instance)), None)
    if facts is None:
        return out({"ok": False, "code": "no_device", "device": dev_id, "next": "devices 로 목록을 본다"})
    backend = device_backends.backend_named(facts.backend)
    if not backend.capabilities.can_shutdown:
        return out({"ok": False, "code": "not_supported", "device": dev_id, "error": "이 기기는 끌 수 없다 (실기기)",
                    "next": None})
    result = backend.shutdown(facts.key, facts.instance)
    if not result["is_ok"]:
        return out({"ok": False, "code": "shutdown_failed", "device": dev_id, "error": result["detail"],
                    "next": "device list 로 상태를 본다"})
    # lease 는 남긴다 — 설정 되돌리기 기록을 잃지 않게 (반납은 device release)
    device_claims.set_pool_booted(key, False)
    return out({"action": "shutdown", "platform": platform, "device": dev_id, "key": facts.key,
                "summary": f"{facts.name} 를 껐다", "next": None})
