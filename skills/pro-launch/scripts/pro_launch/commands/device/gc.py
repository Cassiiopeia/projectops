"""`device gc` — 기기 정리: 기본은 보고만, --apply 때만 지우고 끈다 (#955).

--apply 가 하는 일 3개: 기한 지난 임시 기기 삭제 · 원장이 켜 둔 채 버려진 기기 끄기 · 쓸 수 없게 된 시뮬레이터 삭제.
기록 없는 기기 · 공들인 상태 기기 · 짝 깨진 AVD 는 보고만 한다.
"""
from __future__ import annotations

from pro_launch.runtime import device_backends, device_claims, device_gc, device_marks
from pro_launch.runtime.output import out

BYTES_PER_GB = 1024 ** 3


def _gb(size: int) -> float:
    return round(size / BYTES_PER_GB, 2)


def _apply_row(row: dict) -> dict:
    """계획 한 줄 실행 > {key, action, is_done, detail}."""
    backend = device_backends.backend_named(row["backend"])
    if row["action"] == device_gc.ACTION_SHUTDOWN:
        result = backend.shutdown(row["key"], row["instance"])
        if result["is_ok"]:
            device_claims.set_pool_booted(row["key"], False)
        return {"key": row["key"], "action": row["action"], "is_done": result["is_ok"], "detail": result["detail"]}
    if row["is_booted"]:
        backend.shutdown(row["key"], row["instance"])
    result = backend.delete(row["key"])
    if result["is_ok"]:
        device_marks.forget_device(row["key"])
    return {"key": row["key"], "action": row["action"], "is_done": result["is_ok"], "detail": result["detail"],
            "bytes": row["bytes"]}


def run_gc(args) -> int:
    is_every_size_counted = bool(getattr(args, "sizes", False))
    plan = device_gc.build_plan(is_every_size_counted)
    actionable = [row for row in plan.rows if row["action"] != device_gc.ACTION_KEEP]
    summary_counts = {"delete": sum(r["action"] == "delete" for r in plan.rows),
                      "shutdown": sum(r["action"] == "shutdown" for r in plan.rows),
                      "unavailable": len(plan.unavailable)}
    report = {"devices": plan.rows, "unavailable": plan.unavailable, "orphan_avds": plan.orphan_avds,
              "total_gb": _gb(sum(r["bytes"] for r in plan.rows)) if is_every_size_counted else None,
              "reclaimable_gb": _gb(plan.bytes_of(device_gc.ACTION_DELETE) + sum(u["bytes"] for u in plan.unavailable)),
              "unrecorded_gb": (_gb(sum(r["bytes"] for r in plan.rows if r["origin"] == "unrecorded"))
                                if is_every_size_counted else None)}
    if not args.apply:
        return out({"action": "gc", "applied": False, **report,
                    "summary": (f"기기 {len(plan.rows)}대 · 지울 임시 기기 {summary_counts['delete']} · "
                                f"끌 기기 {summary_counts['shutdown']} · 쓸 수 없는 시뮬레이터 {summary_counts['unavailable']} · "
                                f"정리하면 {report['reclaimable_gb']}GB"
                                + (f" · 기록 없는 기기 {report['unrecorded_gb']}GB(손대지 않음)" if is_every_size_counted
                                   else " · 전체 크기는 --sizes")),
                    "next": "device gc --apply  # 위 계획대로 지우고 끈다" if actionable or plan.unavailable else None})
    results = [_apply_row(row) for row in actionable]
    unavailable_result = None
    if plan.unavailable:
        ios = next(b for b in device_backends.BACKENDS if hasattr(b, "delete_unavailable"))
        unavailable_result = ios.delete_unavailable()
    freed = sum(r.get("bytes") or 0 for r in results if r["is_done"] and r["action"] == device_gc.ACTION_DELETE)
    if unavailable_result and unavailable_result["is_ok"]:
        freed += sum(u["bytes"] for u in plan.unavailable)
    failed = [r for r in results if not r["is_done"]]
    return out({"ok": not failed, "code": "partial" if failed else "ok", "action": "gc", "applied": True, **report,
                "results": results, "unavailable_result": unavailable_result, "freed_gb": _gb(freed),
                "summary": f"정리 {len(results) - len(failed)}/{len(results)} · 확보 {_gb(freed)}GB",
                "next": "실패한 항목의 detail 을 본다" if failed else None})
