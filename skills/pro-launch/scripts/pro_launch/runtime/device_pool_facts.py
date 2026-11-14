"""Gathering decision inputs: device facts + ledger > Candidate · host resources·memory budget > PoolContext · limits and sources (#953 · #954 · #964).

Decisions (device_pool) stay pure functions; reading devices·ledger·host happens here.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from pro_launch.runtime import device_backends, device_capacity, device_claims, device_ledger, host_resources
from pro_launch.runtime.device_marks import mark_label
from pro_launch.runtime.device_pool import Candidate, PoolContext

# Default combined wait limit (min) — launch.devices.wait_limit_minutes
WAIT_LIMIT_DEFAULT_MINUTES = 10
# Minimum free disk (GB): below this no new device is created (launch.devices.min_free_disk_gb)
# No ratio — on a big disk even 45GB free counted as "low" (observed)
MIN_FREE_DISK_GB_DEFAULT = 20
BYTES_PER_GB = 1024 ** 3


def devices_config() -> dict:
    return (device_claims.common_config.get_section("launch") or {}).get("devices") or {}


def _positive(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def disk_status(path: Path | None = None) -> dict:
    """{free_gb, minimum_gb, is_low} — for the home disk where virtual devices pile up."""
    minimum_gb = _positive(devices_config().get("min_free_disk_gb")) or MIN_FREE_DISK_GB_DEFAULT
    usage = shutil.disk_usage(path or Path.home())
    free_gb = usage.free / BYTES_PER_GB
    return {"free_gb": round(free_gb, 1), "minimum_gb": minimum_gb, "is_low": free_gb < minimum_gb}


def wait_limit_minutes() -> tuple[float, str]:
    configured = _positive(devices_config().get("wait_limit_minutes"))
    return (configured, "config") if configured else (WAIT_LIMIT_DEFAULT_MINUTES, "default")


def limits_view() -> dict:
    """Limits used for the decision and their sources (limits field of the response)."""
    wait_minutes, wait_source = wait_limit_minutes()
    disk = disk_status()
    return {"wait_limit_minutes": {"value": wait_minutes, "source": wait_source},
            "lease_idle_minutes": {"value": device_claims.lease_idle_seconds() / 60,
                                   "source": "config" if _positive(devices_config().get("lease_idle_minutes")) else "default"},
            "capacity": device_capacity.capacity_view(),
            "min_free_disk_gb": {"value": disk["minimum_gb"], "free_gb": disk["free_gb"],
                                 "source": "config" if _positive(devices_config().get("min_free_disk_gb")) else "default"}}


def build_candidates(platform: str) -> list[Candidate]:
    """Device facts + ledger > decision inputs. Host liveness is checked once per pid."""
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
    """Host memory · disk · memory budget of running virtual devices · whether creating is possible > PoolContext."""
    memory = host_resources.read_memory()
    wait_minutes, _ = wait_limit_minutes()
    return PoolContext(pressure=host_resources.pressure_level(memory),
                       waited_seconds=waited_seconds, wait_limit_seconds=wait_minutes * 60,
                       can_create=any(b.capabilities.can_create for b in device_backends.backends_for(platform)),
                       is_disk_low=disk_status()["is_low"],
                       boot_block=device_capacity.boot_block_reason(platform, booted_virtual_counts(), memory))


def booted_virtual_counts() -> dict[str, int]:
    """Running virtual device count > {platform: count} (physical devices excluded since they use no memory). Counted whichever session booted them."""
    counts: dict[str, int] = {}
    for facts in device_backends.all_device_facts():
        if facts.is_booted and not device_backends.backend_named(facts.backend).capabilities.is_physical:
            counts[facts.platform] = counts.get(facts.platform, 0) + 1
    return counts
