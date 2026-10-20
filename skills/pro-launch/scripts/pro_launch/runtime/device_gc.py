"""기기 정리 계획: 원장 + 기기 사실 > 지울 것 · 끌 것 · 보고만 할 것 (#955).

지우는 것은 원장이 만든 임시 기기뿐이다 — 기한이 지났고, 아무도 빌리지 않았고, 공들인 상태가 없을 때.
기록 없는 기기 · mark 있는 기기 · 사람이 켠 기기는 손대지 않고 크기와 이유만 보고한다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from pro_launch.runtime import device_backends, device_claims, device_ledger
from pro_launch.runtime.device_marks import is_protected

# 원장이 켠 기기를 아무도 안 쓴 채 이만큼 두면 끈다 (초, 20분)
POOL_BOOTED_IDLE_SHUTDOWN_SECONDS = 20 * 60

ACTION_DELETE = "delete"
ACTION_SHUTDOWN = "shutdown"
ACTION_KEEP = "keep"


@dataclass
class GcPlan:
    """정리 계획. rows 는 기기마다 하나 (action · reason · bytes)."""

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
    """기기 하나 > (action, reason)."""
    temporary = entry.get("temporary") or {}
    is_expired = bool(temporary) and now > float(temporary.get("expires_at") or 0)
    if live_leases:
        return ACTION_KEEP, f"세션 {str(live_leases[0].get('session'))[:8]} 이 빌려 쓰는 중"
    if is_expired and is_protected(entry):
        return ACTION_KEEP, "임시 기기 기한이 지났지만 공들인 상태가 생겼다 — 남길지 사용자에게 묻는다 (adopt 또는 delete --yes)"
    if is_expired:
        return ACTION_DELETE, f"임시 기기 기한 지남 (만든 이유: {temporary.get('reason')})"
    last_used = max([float(lease.get("last_used") or 0) for lease in entry.get("leases") or []]
                    + [float(entry.get("pool_booted_at") or 0)])
    if facts.is_booted and entry.get("pool_booted_at") and now - last_used > POOL_BOOTED_IDLE_SHUTDOWN_SECONDS:
        return ACTION_SHUTDOWN, f"원장이 켰고 {round((now - last_used) / 60)}분째 아무도 안 쓴다"
    if temporary:
        days_left = (float(temporary.get("expires_at") or now) - now) / 86400
        return ACTION_KEEP, f"임시 기기 — {days_left:.1f}일 뒤 정리 대상"
    if is_protected(entry):
        return ACTION_KEEP, "공들인 상태가 기록된 기기 (보호)"
    if not entry.get("origin"):
        return ACTION_KEEP, "원장 기록 없는 기기 — 손대지 않는다 (필요 없으면 사용자 확인 뒤 device delete --yes)"
    return ACTION_KEEP, "원장에 올린 기기"


def build_plan(is_every_size_counted: bool = False) -> GcPlan:
    """지금 기기·원장으로 정리 계획을 만든다 (아무것도 바꾸지 않는다).

    크기는 지우거나 끌 기기 · 임시 기기만 센다 — 전부 세면 수십 GB 를 훑느라 수십 초 걸린다(실측 42초). 전부는 is_every_size_counted.
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
