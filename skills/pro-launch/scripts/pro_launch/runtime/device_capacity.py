"""기기 켜기 예산: 종류별 메모리 비용 · 기기 예산 · 여유분 (#964). 값은 device benchmark 가 설정에 넣는다(없으면 기본값).

켜기 판정 2가지: 켜진 기기 비용 합 + 새 기기 <= 예산 · 지금 남은 메모리 >= 새 기기 + 여유분
"""
from __future__ import annotations

import time

from common import config as common_config

from pro_launch.runtime import host_resources

# 재기 전 기본 비용 (MB) — 실측(2026-10-21, 18GB 맥): iOS 시뮬레이터 약 1GB · Android 에뮬레이터 약 5.6GB(footprint)
DEFAULT_BOOT_COST_MB = {"ios": 1500, "android": 6000}
# 지금 판정에서 남겨 둘 여유 (MB) — 호스트·다른 세션 몫
DEFAULT_MEMORY_RESERVE_MB = 3072
# 재기 전 기기 예산: 전체 RAM 에서 호스트 몫을 뺀 것 (MB)
HOST_SHARE_MB = 8192
# 이보다 오래된 측정은 다시 재라고 권한다 (일)
BENCHMARK_STALE_DAYS = 30
SECONDS_PER_DAY = 24 * 60 * 60


def devices_settings() -> dict:
    return (common_config.get_section("launch") or {}).get("devices") or {}


def _positive(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def boot_cost_mb(platform: str) -> tuple[int, str]:
    """(그 종류 기기 하나의 메모리 비용, 출처 benchmark|default)."""
    measured = _positive((devices_settings().get("boot_cost_mb") or {}).get(platform))
    if measured:
        return int(measured), "benchmark"
    return DEFAULT_BOOT_COST_MB.get(platform, max(DEFAULT_BOOT_COST_MB.values())), "default"


def memory_reserve_mb() -> int:
    return int(_positive(devices_settings().get("memory_reserve_mb")) or DEFAULT_MEMORY_RESERVE_MB)


def memory_budget_mb(total_mb: int | None) -> tuple[int | None, str]:
    """(기기 예산, 출처 benchmark|default). RAM 을 못 읽고 측정도 없으면 (None, unknown) — 예산 판정은 건너뛴다."""
    measured = _positive(devices_settings().get("memory_budget_mb"))
    if measured:
        return int(measured), "benchmark"
    if not total_mb:
        return None, "unknown"
    return max(0, total_mb - HOST_SHARE_MB), "default"


def boot_block_reason(platform: str, booted_counts: dict[str, int], memory: dict | None = None) -> str | None:
    """새 기기 하나를 켜면 안 되는 이유 (예산 초과 · 지금 여유 부족). 켜도 되면 None."""
    memory = memory if memory is not None else host_resources.read_memory()
    cost, _ = boot_cost_mb(platform)
    budget, _ = memory_budget_mb(memory.get("total_mb"))
    used = sum(boot_cost_mb(kind)[0] * count for kind, count in booted_counts.items())
    if budget is not None and used + cost > budget:
        counts = ", ".join(f"{kind} {count}대" for kind, count in booted_counts.items() if count) or "없음"
        return (f"기기 예산 초과 — 켜진 기기({counts}) {used}MB + 새 {platform} {cost}MB > 예산 {budget}MB "
                f"(device benchmark 로 이 컴퓨터 값을 잴 수 있다)")
    available = memory.get("available_mb")
    reserve = memory_reserve_mb()
    if available is not None and available < cost + reserve:
        return f"지금 남은 메모리 {available}MB 가 새 {platform} 기기({cost}MB) + 여유분({reserve}MB) 보다 적다"
    return None


def capacity_view(memory: dict | None = None) -> dict:
    """응답·doctor 용 요약: 비용 · 예산 · 여유분 · 측정 시각 · 다시 재야 하나."""
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
    """측정 결과를 설정에 넣는다 (config 전체를 읽어 launch.devices 만 바꾼다 — 다른 섹션 보존)."""
    data = common_config.load() or {}
    launch = data.setdefault("launch", {})
    devices = launch.setdefault("devices", {})
    devices["boot_cost_mb"] = {**(devices.get("boot_cost_mb") or {}), **costs}
    devices["memory_budget_mb"] = budget_mb
    devices["memory_reserve_mb"] = reserve_mb
    devices["benchmark"] = {**details, "measured_at": time.time()}
    common_config.save(data)
