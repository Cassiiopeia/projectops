"""Device prepared states (mark) · origin · temporary device records (#954).

mark: state not readable from outside the device — sign-in · test data · permissions · settings. kind·name are free strings (no hard-coded provider list).
Devices with any mark are protected: excluded from auto cleanup, and wipe·delete only with --yes.
origin: recorded (made by create) · adopted (existing device added to the ledger). unrecorded if absent.
"""
from __future__ import annotations

import time

from common import config as common_config

from pro_launch.runtime import device_ledger
from pro_launch.runtime.device_claims import resolve_instance_key
from pro_launch.runtime.session_identity import session_identity

# Recommended kinds (not enforced — for docs and help)
RECOMMENDED_MARK_KINDS = ("login", "data", "permission", "config", "other")
# Default mark check period (days) — marked stale past it (launch.devices.mark_stale_days)
MARK_STALE_DAYS_DEFAULT = 14
# Default retention for temporary devices (days) — launch.devices.temporary_ttl_days
TEMPORARY_TTL_DAYS_DEFAULT = 3
ORIGIN_RECORDED = "recorded"
ORIGIN_ADOPTED = "adopted"
SECONDS_PER_DAY = 24 * 60 * 60


def _config_days(key: str, default: int) -> float:
    value = ((common_config.get_section("launch") or {}).get("devices") or {}).get(key)
    return float(value) if isinstance(value, (int, float)) and value > 0 else float(default)


def mark_stale_seconds() -> float:
    return _config_days("mark_stale_days", MARK_STALE_DAYS_DEFAULT) * SECONDS_PER_DAY


def temporary_ttl_days() -> float:
    return _config_days("temp_ttl_days", TEMPORARY_TTL_DAYS_DEFAULT)


def mark_label(mark: dict) -> str:
    """kind:name (same shape as acquire --need)."""
    return f"{mark.get('kind')}:{mark.get('name')}"


def mark_views(entry: dict, now: float | None = None) -> list[dict]:
    """mark list for responses (with is_stale)."""
    current = now or time.time()
    limit = mark_stale_seconds()
    def last_verified(mark: dict) -> float:
        # verified_at 0 means "unverified" (clone) — do not substitute recorded_at
        value = mark.get("verified_at")
        return float(value if value is not None else mark.get("recorded_at") or 0)

    return [{**mark, "label": mark_label(mark), "is_stale": current - last_verified(mark) > limit}
            for mark in entry.get("marks") or []]


def is_protected(entry: dict) -> bool:
    return bool(entry.get("marks"))


def entry_of(dev_id: str) -> tuple[str, dict]:
    key = resolve_instance_key(dev_id)
    return key, device_ledger.read_ledger()["devices"].get(key) or {}


def _entry(ledger: dict, key: str) -> dict:
    return ledger["devices"].setdefault(key, {"leases": [], "settings": []})


def add_mark(dev_id: str, kind: str, name: str, note: str | None = None) -> dict:
    """Record a mark (same kind·name updates — first record time kept). Without an origin, it is added as adopted."""
    key, now = resolve_instance_key(dev_id), time.time()

    def mutate(ledger: dict) -> dict:
        entry = _entry(ledger, key)
        entry.setdefault("origin", ORIGIN_ADOPTED)
        marks = entry.setdefault("marks", [])
        found = next((m for m in marks if m.get("kind") == kind and m.get("name") == name), None)
        if found is None:
            found = {"kind": kind, "name": name, "recorded_at": now}
            marks.append(found)
        found.update({"note": note or found.get("note"), "recorded_by_session": session_identity(), "verified_at": now})
        # Once a prepared state exists it is no longer a new phone
        entry.pop("is_pristine", None)
        return dict(found)

    return device_ledger.update_ledger(mutate)


def remove_mark(dev_id: str, kind: str, name: str) -> bool:
    key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> bool:
        entry = ledger["devices"].get(key) or {}
        before = len(entry.get("marks") or [])
        entry["marks"] = [m for m in entry.get("marks") or [] if not (m.get("kind") == kind and m.get("name") == name)]
        return len(entry["marks"]) < before

    return device_ledger.update_ledger(mutate)


def verify_mark(dev_id: str, kind: str, name: str) -> dict | None:
    """Confirmed the mark is still alive — update verified_at. None if missing."""
    key, now = resolve_instance_key(dev_id), time.time()

    def mutate(ledger: dict) -> dict | None:
        entry = ledger["devices"].get(key) or {}
        found = next((m for m in entry.get("marks") or [] if m.get("kind") == kind and m.get("name") == name), None)
        if found is not None:
            found["verified_at"] = now
        return dict(found) if found else None

    return device_ledger.update_ledger(mutate)


def adopt_device(dev_id: str) -> str:
    """Add a device missing from the ledger > origin (unchanged if already present)."""
    key = resolve_instance_key(dev_id)
    return device_ledger.update_ledger(lambda ledger: _entry(ledger, key).setdefault("origin", ORIGIN_ADOPTED))


def record_created(key: str, reason: str, ttl_days: float, backend: str) -> dict:
    """Record a temporary device made by create > temporary record. Newly created devices are pristine (a new phone nobody used)."""
    now = time.time()
    temporary = {"reason": reason, "created_by_session": session_identity(), "created_at": now,
                 "expires_at": now + ttl_days * SECONDS_PER_DAY, "backend": backend}

    def mutate(ledger: dict) -> dict:
        entry = _entry(ledger, key)
        entry.update({"origin": ORIGIN_RECORDED, "temporary": temporary, "is_pristine": True})
        return temporary

    return device_ledger.update_ledger(mutate)


def copy_marks_as_unverified(source_key: str, target_key: str) -> list[dict]:
    """Copy the source's marks to a clone — verify time set to 0 so it is stale (sign-in on the clone not yet confirmed)."""
    def mutate(ledger: dict) -> list[dict]:
        source = ledger["devices"].get(source_key) or {}
        copied = [{**mark, "verified_at": 0, "note": f"{mark.get('note') or ''} (clone — not verified)".strip(),
                   "recorded_by_session": session_identity()} for mark in source.get("marks") or []]
        target = _entry(ledger, target_key)
        target["marks"] = copied
        target.pop("is_pristine", None)
        return copied

    return device_ledger.update_ledger(mutate)


def clear_pristine(key: str) -> None:
    device_ledger.update_ledger(lambda ledger: (ledger["devices"].get(key) or {}).pop("is_pristine", None))


def reset_after_erase(key: str) -> None:
    """Wiped device: prepared states · settings records are gone > clear marks · settings records and mark it as a new phone."""
    def mutate(ledger: dict) -> None:
        entry = _entry(ledger, key)
        entry["marks"], entry["settings"], entry["is_pristine"] = [], [], True

    device_ledger.update_ledger(mutate)


def forget_device(key: str) -> None:
    """Remove a deleted device's entry from the ledger."""
    device_ledger.update_ledger(lambda ledger: ledger["devices"].pop(key, None))


def record_views() -> dict[str, dict]:
    """Whole-ledger summary > {key: {origin, marks, temporary, is_pristine, lease_count}} (for device records)."""
    now = time.time()
    return {key: {"origin": entry.get("origin"), "marks": mark_views(entry, now), "temporary": entry.get("temporary"),
                  "is_temporary_expired": bool(entry.get("temporary")) and now > float(entry["temporary"].get("expires_at") or 0),
                  "is_pristine": bool(entry.get("is_pristine")), "lease_count": len(entry.get("leases") or [])}
            for key, entry in device_ledger.read_ledger()["devices"].items()}
