"""`device benchmark` — 이 컴퓨터가 가상 기기를 몇 대까지 감당하나 재서 설정에 넣는다 (#964).

기준 상태 > 종류마다 실험 기기 켜서 비용 측정 > 기기 예산 계산 > 설정(launch.devices) 저장 > 사람이 읽는 결과.
다른 세션이 기기를 쓰는 중이면 --yes 없이 시작하지 않는다 (측정이 그 세션을 멈추게 할 수 있다).
"""
from __future__ import annotations

import os

from pro_launch.runtime import device_benchmark, device_capacity, device_claims, device_pool_facts, host_resources
from pro_launch.runtime.output import out
from pro_launch.runtime.session_identity import session_identity

PLATFORMS = ("ios", "android")


def _others_using_devices() -> list[dict]:
    """다른 살아 있는 세션이 빌린 기기."""
    owners = device_claims.owners_by_device()
    seen, rows = set(), []
    for view in owners.values():
        if view["lease_id"] in seen or view["session"] == session_identity():
            continue
        seen.add(view["lease_id"])
        rows.append({"device": view["device"], "session": view["session"], "purpose": view["purpose"]})
    return rows


def _summary(budget_mb: int, costs: dict[str, int]) -> str:
    parts = [f"{platform} up to {budget_mb // cost} (each {cost}MB)" for platform, cost in costs.items() if cost]
    return f"Device budget {budget_mb}MB — " + " · ".join(parts) + " (mixed devices share the budget)"


def run_benchmark(args) -> int:
    platforms = [args.platform] if args.platform in PLATFORMS else list(PLATFORMS)
    # 켜진 기기가 있는 종류는 그 실제 사용량으로 잰다 (새로 켜지 않는다) · --full 이면 늘려 가며 잰다
    running = device_benchmark.measure_running_devices()
    to_boot = [platform for platform in platforms if args.full or platform not in running]
    others = _others_using_devices()
    # 새로 켜는 측정만 다른 세션을 멈추게 할 수 있다 — 켜진 기기만 재는 측정은 그대로 한다
    if others and to_boot and not args.yes:
        return out({"ok": False, "code": "devices_in_use", "others": others, "would_boot": to_boot,
                    "error": "Another session is using devices — booting test devices could stall that session",
                    "next": "Retry after those sessions end, or ask the user and pass --yes"})
    baseline = host_resources.read_memory()
    booted_at_start = device_pool_facts.booted_virtual_counts()
    consumers = device_benchmark.non_device_consumers()
    results = [device_benchmark.measure_platform(platform, bool(args.full)) if platform in to_boot else running[platform]
               for platform in platforms]
    measured = {r["platform"]: r["cost_mb"] for r in results if r.get("cost_mb")}
    if not measured:
        return out({"ok": False, "code": "benchmark_no_room", "results": results, "baseline": baseline,
                    "non_device_consumers": consumers,
                    "error": "Could not boot any test device — " + "; ".join(r.get("skipped") or "" for r in results),
                    "next": "Reduce memory-heavy programs (non_device_consumers) or booted devices, then measure again. Settings were not changed"})
    costs = {platform: measured.get(platform) or device_capacity.boot_cost_mb(platform)[0] for platform in PLATFORMS}
    reserve = device_capacity.memory_reserve_mb()
    # 기기 예산 = 시작 때 남은 메모리 + 이미 켜져 있던 기기들이 쓰던 몫 - 여유분
    in_use = sum(costs.get(platform, 0) * count for platform, count in booted_at_start.items())
    budget = max(0, int((baseline.get("available_mb") or 0) + in_use - reserve))
    details = {"ram_mb": baseline.get("total_mb"), "cores": os.cpu_count(), "results": results,
               "baseline_available_mb": baseline.get("available_mb"),
               "baseline_swap_used_mb": baseline.get("swap_used_mb"), "booted_at_start": booted_at_start,
               "non_device_consumers": consumers, "is_full": bool(args.full)}
    device_capacity.save_benchmark(measured, budget, reserve, details)
    return out({"action": "benchmark", "costs_mb": costs, "measured": list(measured), "memory_budget_mb": budget,
                "memory_reserve_mb": reserve, "results": results, "non_device_consumers": consumers,
                "summary": _summary(budget, costs),
                "next": "acquire · boot now decide with this budget. Measure again if memory conditions change a lot"})
