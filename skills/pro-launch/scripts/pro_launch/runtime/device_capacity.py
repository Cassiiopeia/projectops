"""Device boot budget: memory cost per kind · device budget · headroom (#964). Values are put into settings by device benchmark (defaults otherwise).

2 boot checks: sum of running device costs + new device <= budget · memory free now >= new device + headroom
"""
from __future__ import annotations

import time

from common import config as common_config

from pro_launch.runtime import host_resources

# Default cost before measuring (MB) — observed (2026-10-21, 18GB Mac): iOS simulator about 1GB · Android emulator about 5.6GB (footprint)
DEFAULT_BOOT_COST_MB = {"ios": 1500, "android": 6000}
# Headroom kept in the current check (MB) — share for the host·other sessions
DEFAULT_MEMORY_RESERVE_MB = 3072
# Device budget before measuring: total RAM minus the host share (MB)
HOST_SHARE_MB = 8192
# Measurements older than this suggest re-measuring (days)
BENCHMARK_STALE_DAYS = 30
SECONDS_PER_DAY = 24 * 60 * 60


def devices_settings() -> dict:
    return (common_config.get_section("launch") or {}).get("devices") or {}


def _positive(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def boot_cost_mb(platform: str) -> tuple[int, str]:
    """(memory cost of one device of that kind, source benchmark|default)."""
    measured = _positive((devices_settings().get("boot_cost_mb") or {}).get(platform))
    if measured:
        return int(measured), "benchmark"
    return DEFAULT_BOOT_COST_MB.get(platform, max(DEFAULT_BOOT_COST_MB.values())), "default"


def memory_reserve_mb() -> int:
    return int(_positive(devices_settings().get("memory_reserve_mb")) or DEFAULT_MEMORY_RESERVE_MB)


def memory_budget_mb(total_mb: int | None) -> tuple[int | None, str]:
    """(device budget, source benchmark|default). (None, unknown) if RAM is unreadable and there is no measurement — budget check is skipped."""
    measured = _positive(devices_settings().get("memory_budget_mb"))
    if measured:
        return int(measured), "benchmark"
    if not total_mb:
        return None, "unknown"
    return max(0, total_mb - HOST_SHARE_MB), "default"


def boot_block_reason(platform: str, booted_counts: dict[str, int], memory: dict | None = None) -> str | None:
    """Why one more device must not boot (budget exceeded · not enough headroom now). None if it may boot."""
    memory = memory if memory is not None else host_resources.read_memory()
    cost, _ = boot_cost_mb(platform)
    budget, _ = memory_budget_mb(memory.get("total_mb"))
    used = sum(boot_cost_mb(kind)[0] * count for kind, count in booted_counts.items())
    if budget is not None and used + cost > budget:
        counts = ", ".join(f"{kind} {count}" for kind, count in booted_counts.items() if count) or "none"
        return (f"device budget exceeded — running devices ({counts}) {used}MB + new {platform} {cost}MB > budget {budget}MB "
                f"(device benchmark measures this computer's values)")
    available = memory.get("available_mb")
    reserve = memory_reserve_mb()
    if available is not None and available < cost + reserve:
        return f"available memory {available}MB is less than a new {platform} device ({cost}MB) + reserve ({reserve}MB)"
    return None


def capacity_view(memory: dict | None = None) -> dict:
    """Summary for responses·doctor: cost · budget · headroom · measured at · needs re-measuring."""
    memory = memory if memory is not None else host_resources.read_memory()
    benchmark = devices_settings().get("benchmark") or {}
    measured_at = benchmark.get("measured_at")
    is_stale = bool(measured_at) and time.time() - float(measured_at) > BENCHMARK_STALE_DAYS * SECONDS_PER_DAY
    is_ram_changed = bool(benchmark.get("ram_mb")) and benchmark.get("ram_mb") != memory.get("total_mb")
    budget, budget_source = memory_budget_mb(memory.get("total_mb"))
    return {"boot_cost_mb": {kind: boot_cost_mb(kind)[0] for kind in DEFAULT_BOOT_COST_MB},
            "boot_cost_source": {kind: boot_cost_mb(kind)[1] for kind in DEFAULT_BOOT_COST_MB},
            "memory_budget_mb": budget, "memory_budget_source": budget_source,
            "memory_reserve_mb": memory_reserve_mb(),
            "measured_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(measured_at)) if measured_at else None,
            "should_benchmark": not measured_at or is_stale or is_ram_changed}


def save_benchmark(costs: dict[str, int], budget_mb: int, reserve_mb: int, details: dict) -> None:
    """Put measurement results into settings (reads the whole config and changes only launch.devices — other sections preserved)."""
    data = common_config.load() or {}
    launch = data.setdefault("launch", {})
    devices = launch.setdefault("devices", {})
    devices["boot_cost_mb"] = {**(devices.get("boot_cost_mb") or {}), **costs}
    devices["memory_budget_mb"] = budget_mb
    devices["memory_reserve_mb"] = reserve_mb
    devices["benchmark"] = {**details, "measured_at": time.time()}
    common_config.save(data)
