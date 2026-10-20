"""`device create · clone · erase · delete · mark · unmark · adopt · records` — 기기 수명과 공들인 상태 기록 (#954 · #955).

raw simctl·avdmanager 대신 여기를 거친다: 만든 기기는 이유·기한과 함께 원장에 남고(정리 대상),
mark 가 있는 기기·남이 빌린 기기·사람이 켠 기기는 --yes 없이 지우거나 초기화하지 않는다.
"""
from __future__ import annotations

import time

from pro_launch.commands.device.claims import refuse_other_session_owner
from pro_launch.runtime import device_backends, device_claims, device_marks, device_pool_facts
from pro_launch.runtime.device_backends.base import default_device_name
from pro_launch.runtime.output import out


def _resolve_any(args):
    """꺼진 기기까지 찾는다 > (facts, backend, 오류 응답)."""
    if not args.device:
        return None, None, out({"ok": False, "code": "args_required", "error": "--device 가 필요하다",
                                "next": "device records 또는 devices 로 기기 키(UDID · AVD 이름)를 본다"})
    facts, matches = device_backends.find_device(args.device, getattr(args, "platform", None))
    if facts is None and matches:
        return None, None, out({"ok": False, "code": "device_ambiguous", "error": f"'{args.device}' 이름의 기기가 {len(matches)}대",
                                "candidates": [{"key": f.key, "name": f.name, "os": f.os_version} for f in matches],
                                "next": "--device <키> 로 하나를 고른다"})
    if facts is None:
        return None, None, out({"ok": False, "code": "no_device", "error": f"'{args.device}' 기기를 찾지 못했다",
                                "next": "devices 로 목록을 본다"})
    return facts, device_backends.backend_named(facts.backend), None


def _resource_refusal(action: str, args) -> int | None:
    """만들기·복제 전 디스크 확인 — --yes 로만 넘는다.

    켜지 않으므로 메모리는 보지 않는다 (켤 때 acquire 가 메모리 압박을 따로 본다).
    """
    if args.yes:
        return None
    disk = device_pool_facts.disk_status()
    if disk["is_low"]:
        return out({"ok": False, "code": "resources_low", "action": action, "disk": disk,
                    "error": f"디스크 여유가 {disk['free_gb']}GB 다 (하한 {disk['minimum_gb']}GB)",
                    "next": "device gc 로 정리할 것이 있는지 본다. 그래도 필요하면 사용자에게 묻고 --yes"})
    return None


def run_create(args) -> int:
    if args.platform not in ("ios", "android") or not args.reason:
        return out({"ok": False, "code": "args_required", "error": "--platform 과 --reason(왜 새 기기가 필요한가)이 필요하다",
                    "next": "device create --platform ios --reason '#954 두 대 동시 로그인 테스트'"})
    if (refusal := _resource_refusal("create", args)) is not None:
        return refusal
    backend = next((b for b in device_backends.backends_for(args.platform) if b.capabilities.can_create), None)
    if backend is None:
        return out({"ok": False, "code": "not_supported", "error": f"{args.platform} 기기를 만들 수 없다", "next": None})
    name = args.name or default_device_name(time.strftime("%Y%m%d-%H%M%S"))
    created = backend.create(name, args.form or "phone", args.os)
    if not created["is_ok"]:
        return out({"ok": False, "code": "create_failed", "error": created["detail"], "next": "devices 로 기존 기기를 본다"})
    ttl_days = args.ttl_days or device_marks.temporary_ttl_days()
    temporary = device_marks.record_created(created["key"], args.reason, ttl_days, backend.name)
    return out({"action": "create", "platform": args.platform, "device": created["key"], "name": name, "temporary": temporary,
                "summary": f"{name} ({created['key']}) 을 만들었다 — {ttl_days:g}일 뒤 정리 대상",
                "next": f"device acquire --platform {args.platform} --device {created['key']} --purpose '...'"})


def clone_device(facts, backend, name: str | None, reason: str, ttl_days: float | None) -> dict:
    """꺼진 원본 복제 > 응답 dict: 새 기기 기록(임시) + 원본 mark 를 확인 전 상태로 복사."""
    if not backend.capabilities.can_clone:
        return {"ok": False, "code": "not_supported", "device": facts.key, "error": f"{facts.platform} 기기는 복제할 수 없다",
                "next": "device acquire --count 2 로 다른 기기를 받는다"}
    if facts.is_booted:
        return {"ok": False, "code": "source_booted", "device": facts.key,
                "error": "켜져 있는 기기는 복제할 수 없다 (simctl 제약)",
                "next": "원본을 쓰는 세션이 끝나 꺼진 뒤 다시 부른다 (내 것이면 device shutdown 후)"}
    clone_name = name or f"{facts.name} 복제 {time.strftime('%m%d-%H%M')}"
    cloned = backend.clone(facts.key, clone_name)
    if not cloned["is_ok"]:
        return {"ok": False, "code": "clone_failed", "device": facts.key, "error": cloned["detail"], "next": None}
    temporary = device_marks.record_created(cloned["key"], reason, ttl_days or device_marks.temporary_ttl_days(),
                                            backend.name)
    marks = device_marks.copy_marks_as_unverified(facts.key, cloned["key"])
    return {"action": "clone", "platform": facts.platform, "source": facts.key, "device": cloned["key"],
            "name": clone_name, "temporary": temporary, "marks": [device_marks.mark_label(m) for m in marks],
            "summary": f"{facts.name} 를 복제했다 > {clone_name}" + (f" (상태 {len(marks)}개는 확인 전)" if marks else ""),
            "next": ("복제본을 빌려 로그인이 살아 있는지 보고 device mark --verify" if marks
                     else f"device acquire --platform {facts.platform} --device {cloned['key']}")}


def run_clone(args) -> int:
    facts, backend, err = _resolve_any(args)
    if err is not None:
        return err
    if not args.reason:
        return out({"ok": False, "code": "args_required", "error": "--reason(왜 복제가 필요한가)이 필요하다",
                    "next": "device clone --device <원본> --reason '#955 로그인된 기기 두 대'"})
    if (refusal := _resource_refusal("clone", args)) is not None:
        return refusal
    return out(clone_device(facts, backend, args.name, args.reason, args.ttl_days))


def _destructive_refusal(action: str, facts, args) -> int | None:
    """지우기·초기화 거부 사유 3개: 남이 빌림 · 공들인 상태 · 사람이 켠 기기. --yes 로만 넘는다."""
    if args.yes:
        return None
    if (refusal := refuse_other_session_owner(facts.instance or facts.key, action)) is not None:
        return refusal
    key, entry = device_marks.entry_of(facts.key)
    if device_marks.is_protected(entry):
        return out({"ok": False, "code": "device_protected", "action": action, "device": key,
                    "marks": device_marks.mark_views(entry),
                    "error": "공들인 상태가 기록된 기기다 — 지우면 다시 만들어야 한다",
                    "next": "marks 를 사용자에게 보여 주고 정말 지울지 묻는다. 그렇다면 --yes"})
    if facts.is_booted and not entry.get("pool_booted_at") and not entry.get("leases"):
        return out({"ok": False, "code": "device_in_use_unrecorded", "action": action, "device": key,
                    "error": "켜져 있지만 원장 기록이 없다 — 사람이 쓰는 기기일 수 있다",
                    "next": "사용자에게 묻고 --yes"})
    return None


def _shutdown_first(facts, backend) -> dict | None:
    if not facts.is_booted:
        return None
    result = backend.shutdown(facts.key, facts.instance)
    return None if result["is_ok"] else {"ok": False, "code": "shutdown_failed", "device": facts.key,
                                         "error": result["detail"], "next": "device list 로 상태를 본다"}


def run_erase(args) -> int:
    facts, backend, err = _resolve_any(args)
    if err is not None:
        return err
    if (refusal := _destructive_refusal("erase", facts, args)) is not None:
        return refusal
    if (failure := _shutdown_first(facts, backend)) is not None:
        return out(failure)
    result = backend.erase(facts.key)
    if not result["is_ok"]:
        return out({"ok": False, "code": "erase_failed", "device": facts.key, "error": result["detail"], "next": None})
    device_marks.reset_after_erase(facts.key)
    device_claims.set_pool_booted(facts.key, False)
    return out({"action": "erase", "platform": facts.platform, "device": facts.key, "name": facts.name,
                "summary": f"{facts.name} 를 초기화했다 (공들인 상태 기록도 지웠다)", "next": None})


def run_delete(args) -> int:
    facts, backend, err = _resolve_any(args)
    if err is not None:
        return err
    if (refusal := _destructive_refusal("delete", facts, args)) is not None:
        return refusal
    if (failure := _shutdown_first(facts, backend)) is not None:
        return out(failure)
    result = backend.delete(facts.key)
    if not result["is_ok"]:
        return out({"ok": False, "code": "delete_failed", "device": facts.key, "error": result["detail"], "next": None})
    device_marks.forget_device(facts.key)
    return out({"action": "delete", "platform": facts.platform, "device": facts.key, "name": facts.name,
                "summary": f"{facts.name} 를 지웠다", "next": None})


def run_mark(args) -> int:
    facts, _, err = _resolve_any(args)
    if err is not None:
        return err
    if not args.kind or not args.name:
        return out({"ok": False, "code": "args_required", "error": "--kind 와 --name 이 필요하다",
                    "next": "device mark --device $DEV --kind login --name kakao --note 'guardian 계정'"})
    if args.verify:
        verified = device_marks.verify_mark(facts.key, args.kind, args.name)
        if verified is None:
            return out({"ok": False, "code": "mark_not_found", "device": facts.key, "next": "device records 로 기록을 본다"})
        return out({"action": "mark", "device": facts.key, "mark": verified, "summary": f"{args.kind}:{args.name} 확인함"})
    mark = device_marks.add_mark(facts.key, args.kind, args.name, args.note)
    return out({"action": "mark", "device": facts.key, "name": facts.name, "mark": mark,
                "summary": f"{facts.name} 에 {args.kind}:{args.name} 기록 — 이제 정리·초기화에서 보호된다",
                "next": f"다음엔 device acquire --platform {facts.platform} --need {args.kind}:{args.name}"})


def run_unmark(args) -> int:
    facts, _, err = _resolve_any(args)
    if err is not None:
        return err
    is_removed = device_marks.remove_mark(facts.key, args.kind or "", args.name or "")
    return out({"action": "unmark", "device": facts.key, "removed": is_removed,
                "summary": f"{args.kind}:{args.name} " + ("지움" if is_removed else "기록이 없다"), "next": None})


def run_adopt(args) -> int:
    facts, _, err = _resolve_any(args)
    if err is not None:
        return err
    origin = device_marks.adopt_device(facts.key)
    return out({"action": "adopt", "device": facts.key, "name": facts.name, "origin": origin,
                "summary": f"{facts.name} 를 원장에 올렸다 ({origin})",
                "next": "공들인 상태(로그인·데이터)가 있으면 device mark 로 기록한다"})


def run_records(args) -> int:
    """기기마다 사실 + 원장 기록 (출처 · mark · 임시 기한 · 빌림)."""
    records = device_marks.record_views()
    owners = device_claims.owners_by_device()
    rows = []
    for facts in device_backends.all_device_facts(getattr(args, "platform", None)):
        record = records.get(facts.key) or {}
        rows.append({"key": facts.key, "name": facts.name, "platform": facts.platform, "form": facts.form,
                     "os": facts.os_version, "is_booted": facts.is_booted, "origin": record.get("origin") or "unrecorded",
                     "marks": record.get("marks") or [], "temporary": record.get("temporary"),
                     "is_temporary_expired": record.get("is_temporary_expired", False), "is_pristine": record.get("is_pristine", False),
                     "owner": owners.get(facts.key) or owners.get(facts.instance or "")})
    return out({"action": "records", "devices": rows, "limits": device_pool_facts.limits_view(),
                "summary": f"기기 {len(rows)}대 · 공들인 상태 {sum(bool(r['marks']) for r in rows)}대 · "
                           f"임시 {sum(bool(r['temporary']) for r in rows)}대",
                "next": None})
