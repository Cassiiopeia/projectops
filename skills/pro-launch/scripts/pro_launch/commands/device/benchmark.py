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
    parts = [f"{platform} 최대 {budget_mb // cost}대 (한 대 {cost}MB)" for platform, cost in costs.items() if cost]
    return f"기기 예산 {budget_mb}MB — " + " · ".join(parts) + " (섞어 켜면 예산 안에서 합산)"


def run_benchmark(args) -> int:
    others = _others_using_devices()
    if others and not args.yes:
        return out({"ok": False, "code": "devices_in_use", "others": others,
                    "error": "다른 세션이 기기를 쓰는 중이다 — 측정이 그 세션을 멈추게 할 수 있다",
                    "next": "그 세션들이 끝난 뒤 다시 하거나, 사용자에게 묻고 --yes"})
    platforms = [args.platform] if args.platform in PLATFORMS else list(PLATFORMS)
    baseline = host_resources.read_memory()
    booted_at_start = device_pool_facts.booted_virtual_counts()
    consumers = device_benchmark.non_device_consumers()
    results = [device_benchmark.measure_platform(platform, bool(args.full)) for platform in platforms]
    measured = {r["platform"]: r["cost_mb"] for r in results if r.get("cost_mb")}
    if not measured:
        return out({"ok": False, "code": "benchmark_no_room", "results": results, "baseline": baseline,
                    "non_device_consumers": consumers,
                    "error": "실험 기기를 하나도 켜지 못했다 — " + "; ".join(r.get("skipped") or "" for r in results),
                    "next": "메모리를 쓰는 프로그램(non_device_consumers)이나 켜진 기기를 줄인 뒤 다시 잰다. 설정은 바꾸지 않았다"})
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
                "next": "이제 acquire · boot 가 이 예산으로 판단한다. 메모리 사정이 크게 바뀌면 다시 잰다"})
