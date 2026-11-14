"""Device cleanup plan: ledger + device facts > what to delete · power off · only report (#955).

Only temporary devices the ledger created are deleted — when expired, borrowed by nobody, and without prepared states.
Unrecorded devices · devices with marks · human-started devices are left alone; only size and reason are reported.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from pro_launch.runtime import device_backends, device_claims, device_ledger
from pro_launch.runtime.device_marks import is_protected

# Power off a ledger-booted device left unused this long (s, 20 min)
POOL_BOOTED_IDLE_SHUTDOWN_SECONDS = 20 * 60

ACTION_DELETE = "delete"
ACTION_SHUTDOWN = "shutdown"
ACTION_KEEP = "keep"


@dataclass
class GcPlan:
    """Cleanup plan. rows has one entry per device (action · reason · bytes)."""

    rows: list[dict] = field(default_factory=list)
    unavailable: list[dict] = field(default_factory=list)
    orphan_avds: list[dict] = field(default_factory=list)

    def bytes_of(self, action: str) -> int:
        return sum(row["bytes"] for row in self.rows if row["action"] == action)


def _row(facts, action: str, reason: str, size: int, entry: dict) -> dict:
    return {"key": facts.key, "name": facts.name, "platform": facts.platform, "backend": facts.backend,
            "instance": facts.instance, "is_booted": facts.is_booted, "action": action, "reason": reason,
            "bytes": size, "origin": entry.get("origin") or "unrecorded",
            "marks": [f"{m.get('kind')}:{m.get('name')}" for m in entry.get("marks") or []]}


def _decide_row(facts, entry: dict, live_leases: list[dict], now: float) -> tuple[str, str]:
    """One device > (action, reason)."""
    temporary = entry.get("temporary") or {}
    is_expired = bool(temporary) and now > float(temporary.get("expires_at") or 0)
    if live_leases:
        return ACTION_KEEP, f"borrowed by session {str(live_leases[0].get('session'))[:8]}"
    if is_expired and is_protected(entry):
        return ACTION_KEEP, "temporary device expired but has a marked state now — ask the user whether to keep it (adopt or delete --yes)"
    if is_expired:
        return ACTION_DELETE, f"temporary device expired (created for: {temporary.get('reason')})"
    last_used = max([float(lease.get("last_used") or 0) for lease in entry.get("leases") or []]
                    + [float(entry.get("pool_booted_at") or 0)])
    if facts.is_booted and entry.get("pool_booted_at") and now - last_used > POOL_BOOTED_IDLE_SHUTDOWN_SECONDS:
        return ACTION_SHUTDOWN, f"booted by the pool, unused for {round((now - last_used) / 60)} min"
    if temporary:
        days_left = (float(temporary.get("expires_at") or now) - now) / 86400
        return ACTION_KEEP, f"temporary device — cleaned up in {days_left:.1f} days"
    if is_protected(entry):
        return ACTION_KEEP, "device with a marked state (protected)"
    if not entry.get("origin"):
        return ACTION_KEEP, "device not in the ledger — left alone (if unneeded, confirm with the user, then device delete --yes)"
    return ACTION_KEEP, "device registered in the ledger"


def build_plan(is_every_size_counted: bool = False) -> GcPlan:
    """Build a cleanup plan from current devices·ledger (changes nothing).

    Sizes are counted only for devices to delete or power off · temporary devices — counting all scans tens of GB and takes tens of seconds (observed 42 s). All: is_every_size_counted.
    """
    ledger, now, probe = device_ledger.read_ledger(), time.time(), device_claims._HostProbe()
    plan = GcPlan()
    for backend in device_backends.BACKENDS:
        for facts in backend.list_devices():
            entry = ledger["devices"].get(facts.key) or {}
            live = [lease for lease in entry.get("leases") or [] if device_claims.is_lease_live(lease, now, probe)]
            action, reason = _decide_row(facts, entry, live, now)
            is_size_needed = is_every_size_counted or action != ACTION_KEEP or bool(entry.get("temporary"))
            size = backend.disk_bytes(facts.key) if is_size_needed else 0
            plan.rows.append(_row(facts, action, reason, size, entry))
        if hasattr(backend, "unavailable_devices"):
            plan.unavailable += backend.unavailable_devices()
        if hasattr(backend, "orphan_avd_entries"):
            plan.orphan_avds += backend.orphan_avd_entries()
    return plan
