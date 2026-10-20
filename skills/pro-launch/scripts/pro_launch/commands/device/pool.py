"""`device release` · `device shutdown` — 반납하며 이 빌림이 켠 것을 끈다 · 끈다 (#953). 빌리기는 acquire.py.

release: 설정 되돌림 > lease 삭제 > 이 빌림이 켰고 남은 소유가 없으면 끔.
"""
from __future__ import annotations

from pro_launch.commands.device.claims import refuse_other_session_owner, resolve_device, run_restore_commands
from pro_launch.runtime import device_backends, device_claims, device_ledger
from pro_launch.runtime.output import out
from pro_launch.runtime.session_identity import session_identity


def _release_one(dev_id: str, lease_id: str | None, is_keep_booted: bool) -> dict:
    """lease 하나 반납 > 결과 행 {device, released, restored, shutdown, shutdown_reason}."""
    released = device_claims.release_device(dev_id, lease_id)
    if released is None:
        return {"device": dev_id, "released": False, "restored": [], "shutdown": False, "shutdown_reason": "no_lease"}
    restored = [run_restore_commands(setting) for setting in released["settings"]]
    lease, key = released["lease"], released["owner"]["key"]
    entry = device_ledger.read_ledger()["devices"].get(key) or {}
    is_pool_booted = bool(lease.get("is_booted_by_lease") or entry.get("pool_booted_at"))
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
