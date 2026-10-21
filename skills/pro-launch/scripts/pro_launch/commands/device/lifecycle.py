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
        return None, None, out({"ok": False, "code": "args_required", "error": "--device is required",
                                "next": "See the device key (UDID · AVD name) with device records or devices"})
    facts, matches = device_backends.find_device(args.device, getattr(args, "platform", None))
    if facts is None and matches:
        return None, None, out({"ok": False, "code": "device_ambiguous", "error": f"{len(matches)} devices are named '{args.device}'",
                                "candidates": [{"key": f.key, "name": f.name, "os": f.os_version} for f in matches],
                                "next": "Pick one with --device <key>"})
    if facts is None:
        return None, None, out({"ok": False, "code": "no_device", "error": f"Device '{args.device}' not found",
                                "next": "See the list with devices"})
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
                    "error": f"Only {disk['free_gb']}GB of disk free (minimum {disk['minimum_gb']}GB)",
                    "next": "Check with device gc for anything to clean up. If still needed, ask the user and pass --yes"})
    return None


def creation_reason(args) -> str | None:
    """--reason, 없으면 --purpose (acquire 와 헷갈려 쓴다, #972)."""
    return args.reason or getattr(args, "purpose", None)


def run_create(args) -> int:
    args.reason = creation_reason(args)
    if args.platform not in ("ios", "android") or not args.reason:
        return out({"ok": False, "code": "args_required", "error": "--platform and --reason (why a new device is needed) are required",
                    "next": "device create --platform ios --reason '#954 two-device concurrent login test'"})
    if (refusal := _resource_refusal("create", args)) is not None:
        return refusal
    backend = next((b for b in device_backends.backends_for(args.platform) if b.capabilities.can_create), None)
    if backend is None:
        return out({"ok": False, "code": "not_supported", "error": f"Cannot create a {args.platform} device", "next": None})
    name = args.name or default_device_name(time.strftime("%Y%m%d-%H%M%S"))
    created = backend.create(name, args.form or "phone", args.os)
    if not created["is_ok"]:
        return out({"ok": False, "code": "create_failed", "error": created["detail"], "next": "See existing devices with devices"})
    ttl_days = args.ttl_days or device_marks.temporary_ttl_days()
    temporary = device_marks.record_created(created["key"], args.reason, ttl_days, backend.name)
    return out({"action": "create", "platform": args.platform, "device": created["key"], "name": name, "temporary": temporary,
                "summary": f"Created {name} ({created['key']}) — eligible for cleanup in {ttl_days:g} days",
                "next": f"device acquire --platform {args.platform} --device {created['key']} --purpose '...'"})


def clone_device(facts, backend, name: str | None, reason: str, ttl_days: float | None) -> dict:
    """꺼진 원본 복제 > 응답 dict: 새 기기 기록(임시) + 원본 mark 를 확인 전 상태로 복사."""
    if not backend.capabilities.can_clone:
        return {"ok": False, "code": "not_supported", "device": facts.key, "error": f"{facts.platform} devices cannot be cloned",
                "next": "Get another device with device acquire --count 2"}
    if facts.is_booted:
        return {"ok": False, "code": "source_booted", "device": facts.key,
                "error": "A booted device cannot be cloned (simctl limitation)",
                "next": "Call again after the session using the source ends and it shuts down (if it is yours, after device shutdown)"}
    clone_name = name or f"{facts.name} clone {time.strftime('%m%d-%H%M')}"
    cloned = backend.clone(facts.key, clone_name)
    if not cloned["is_ok"]:
        return {"ok": False, "code": "clone_failed", "device": facts.key, "error": cloned["detail"], "next": None}
    temporary = device_marks.record_created(cloned["key"], reason, ttl_days or device_marks.temporary_ttl_days(),
                                            backend.name)
    marks = device_marks.copy_marks_as_unverified(facts.key, cloned["key"])
    return {"action": "clone", "platform": facts.platform, "source": facts.key, "device": cloned["key"],
            "name": clone_name, "temporary": temporary, "marks": [device_marks.mark_label(m) for m in marks],
            "summary": f"Cloned {facts.name} > {clone_name}" + (f" ({len(marks)} states not yet verified)" if marks else ""),
            "next": ("Borrow the clone, check the login is still valid, then device mark --verify" if marks
                     else f"device acquire --platform {facts.platform} --device {cloned['key']}")}


def run_clone(args) -> int:
    facts, backend, err = _resolve_any(args)
    if err is not None:
        return err
    args.reason = creation_reason(args)
    if not args.reason:
        return out({"ok": False, "code": "args_required", "error": "--reason (why a clone is needed) is required",
                    "next": "device clone --device <source> --reason '#955 two logged-in devices'"})
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
                    "error": "This device has recorded prepared state — deleting it means rebuilding that state",
                    "next": "Show the marks to the user and ask whether to really delete. If yes, --yes"})
    if facts.is_booted and not entry.get("pool_booted_at") and not entry.get("leases"):
        return out({"ok": False, "code": "device_in_use_unrecorded", "action": action, "device": key,
                    "error": "Booted but not in the ledger — a person may be using this device",
                    "next": "Ask the user, then --yes"})
    return None


def _shutdown_first(facts, backend) -> dict | None:
    if not facts.is_booted:
        return None
    result = backend.shutdown(facts.key, facts.instance)
    return None if result["is_ok"] else {"ok": False, "code": "shutdown_failed", "device": facts.key,
                                         "error": result["detail"], "next": "Check the state with device list"}


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
                "summary": f"Erased {facts.name} (its prepared-state records were cleared too)", "next": None})


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
                "summary": f"Deleted {facts.name}", "next": None})


def run_mark(args) -> int:
    facts, _, err = _resolve_any(args)
    if err is not None:
        return err
    if not args.kind or not args.name:
        return out({"ok": False, "code": "args_required", "error": "--kind and --name are required",
                    "next": "device mark --device $DEV --kind login --name kakao --note 'guardian account'"})
    if args.verify:
        verified = device_marks.verify_mark(facts.key, args.kind, args.name)
        if verified is None:
            return out({"ok": False, "code": "mark_not_found", "device": facts.key, "next": "See the records with device records"})
        return out({"action": "mark", "device": facts.key, "mark": verified, "summary": f"{args.kind}:{args.name} verified"})
    mark = device_marks.add_mark(facts.key, args.kind, args.name, args.note)
    return out({"action": "mark", "device": facts.key, "name": facts.name, "mark": mark,
                "summary": f"Recorded {args.kind}:{args.name} on {facts.name} — now protected from cleanup and erase",
                "next": f"Next time: device acquire --platform {facts.platform} --need {args.kind}:{args.name}"})


def run_unmark(args) -> int:
    facts, _, err = _resolve_any(args)
    if err is not None:
        return err
    is_removed = device_marks.remove_mark(facts.key, args.kind or "", args.name or "")
    return out({"action": "unmark", "device": facts.key, "removed": is_removed,
                "summary": f"{args.kind}:{args.name} " + ("removed" if is_removed else "not recorded"), "next": None})


def run_adopt(args) -> int:
    facts, _, err = _resolve_any(args)
    if err is not None:
        return err
    origin = device_marks.adopt_device(facts.key)
    return out({"action": "adopt", "device": facts.key, "name": facts.name, "origin": origin,
                "summary": f"Added {facts.name} to the ledger ({origin})",
                "next": "If it has prepared state (login · data), record it with device mark"})


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
                "summary": f"{len(rows)} devices · {sum(bool(r['marks']) for r in rows)} with prepared state · "
                           f"{sum(bool(r['temporary']) for r in rows)} temporary",
                "next": None})
