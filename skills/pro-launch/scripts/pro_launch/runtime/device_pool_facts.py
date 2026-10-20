"""판정 재료 모으기: 기기 사실 + 원장 > Candidate · 호스트 자원 > PoolContext · 한도와 출처 (#953 · #954).

판정(device_pool)은 순수 함수로 두고, 기기·원장·호스트를 읽는 일은 여기서 한다.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from pro_launch.runtime import device_backends, device_claims, device_ledger, host_resources
from pro_launch.runtime.device_marks import mark_label
from pro_launch.runtime.device_pool import Candidate, PoolContext

# 합친 대기 한도 기본값 (분) — launch.devices.wait_limit_minutes
WAIT_LIMIT_DEFAULT_MINUTES = 10
# 디스크 여유 하한 (GB): 이보다 적으면 새 기기를 만들지 않는다 (launch.devices.min_free_disk_gb)
# 비율은 쓰지 않는다 — 큰 디스크에서 45GB 남아도 "부족"이 됐다 (실측)
MIN_FREE_DISK_GB_DEFAULT = 20
# 동시 켜짐 한도 계산: (RAM GB - 호스트 몫) / 기기당 GB, 1~6 대 (launch.devices.max_booted 로 덮어쓴다)
HOST_RESERVED_RAM_GB = 8
RAM_GB_PER_BOOTED_DEVICE = 3
MAX_BOOTED_FLOOR, MAX_BOOTED_CEILING = 1, 6
BYTES_PER_GB = 1024 ** 3


def devices_config() -> dict:
    return (device_claims.common_config.get_section("launch") or {}).get("devices") or {}


def _positive(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def max_booted_limit() -> tuple[int, str]:
    """(동시 켜짐 한도, 출처 config|computed|default)."""
    configured = _positive(devices_config().get("max_booted"))
    if configured:
        return int(configured), "config"
    total_mb = host_resources.read_memory().get("total_mb")
    if not total_mb:
        return MAX_BOOTED_FLOOR + 1, "default"
    computed = int((total_mb / 1024 - HOST_RESERVED_RAM_GB) // RAM_GB_PER_BOOTED_DEVICE)
    return max(MAX_BOOTED_FLOOR, min(MAX_BOOTED_CEILING, computed)), "computed"


def disk_status(path: Path | None = None) -> dict:
    """{free_gb, minimum_gb, is_low} — 가상 기기가 쌓이는 홈 디스크 기준."""
    minimum_gb = _positive(devices_config().get("min_free_disk_gb")) or MIN_FREE_DISK_GB_DEFAULT
    usage = shutil.disk_usage(path or Path.home())
    free_gb = usage.free / BYTES_PER_GB
    return {"free_gb": round(free_gb, 1), "minimum_gb": minimum_gb, "is_low": free_gb < minimum_gb}


def wait_limit_minutes() -> tuple[float, str]:
    configured = _positive(devices_config().get("wait_limit_minutes"))
    return (configured, "config") if configured else (WAIT_LIMIT_DEFAULT_MINUTES, "default")


def limits_view() -> dict:
    """판정에 쓴 한도와 출처 (응답 limits 필드)."""
    wait_minutes, wait_source = wait_limit_minutes()
    max_booted, max_booted_source = max_booted_limit()
    disk = disk_status()
    return {"wait_limit_minutes": {"value": wait_minutes, "source": wait_source},
            "lease_idle_minutes": {"value": device_claims.lease_idle_seconds() / 60,
                                   "source": "config" if _positive(devices_config().get("lease_idle_minutes")) else "default"},
            "max_booted": {"value": max_booted, "source": max_booted_source},
            "min_free_disk_gb": {"value": disk["minimum_gb"], "free_gb": disk["free_gb"],
                                 "source": "config" if _positive(devices_config().get("min_free_disk_gb")) else "default"}}


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
                                        last_used=last_used,
                                        marks=tuple(mark_label(mark) for mark in entry.get("marks") or []),
                                        is_pristine=bool(entry.get("is_pristine"))))
    return candidates


def build_context(platform: str, waited_seconds: float) -> PoolContext:
    """호스트 메모리 · 디스크 · 켜진 가상 기기 수 · 만들기 가능 여부 > PoolContext."""
    booted_count = sum(1 for facts in device_backends.all_device_facts()
                       if facts.is_booted and not device_backends.backend_named(facts.backend).capabilities.is_physical)
    max_booted, _ = max_booted_limit()
    wait_minutes, _ = wait_limit_minutes()
    return PoolContext(pressure=host_resources.memory_summary().get("pressure") or "unknown",
                       waited_seconds=waited_seconds, wait_limit_seconds=wait_minutes * 60,
                       can_create=any(b.capabilities.can_create for b in device_backends.backends_for(platform)),
                       is_disk_low=disk_status()["is_low"], booted_count=booted_count, max_booted=max_booted)
