"""Device ownership (lease): which session holds a device · device-wide settings that session changed (#925 · #953).

Several sessions share one Mac's emulators·simulators. Records live in one place: this computer's shared ledger (`device_ledger`).
Owner = lease (session, host pid). Released immediately when the host dies, or when idle past the limit even if alive.

**Inform, do not block (this module).** Whether to refuse is decided by the caller (dispatcher gate · device command).
"""
from __future__ import annotations

import time
import uuid

from common import config as common_config

from pro_launch.runtime import agent_hosts, device_ledger
from pro_launch.runtime.session_identity import ANONYMOUS_SESSION, session_identity

# Ownership counts as released after this much idle time since last use (30 min, overridden by launch.devices.lease_idle_minutes)
CLAIM_IDLE_EXPIRY_SECONDS = 30 * 60
# Name-only device selectors — cannot tell who holds them, so not recorded
UNNAMED_DEVICE_IDS = ("booted",)

# In-process cache: running id > ledger key · this process's agent host
_KEY_BY_INSTANCE: dict[str, str] = {}
_CURRENT_HOST: dict = {}


def claims_path():
    return device_ledger.ledger_path()


def lease_idle_seconds() -> float:
    """Idle limit (s): setting launch.devices.lease_idle_minutes > default 30 min."""
    devices_config = ((common_config.get_section("launch") or {}).get("devices") or {})
    minutes = devices_config.get("lease_idle_minutes")
    return float(minutes) * 60 if isinstance(minutes, (int, float)) and minutes > 0 else CLAIM_IDLE_EXPIRY_SECONDS


def resolve_instance_key(dev_id: str) -> str:
    """Running id > ledger key. Android emulator serial > AVD name (serial as is if unreadable), others as is."""
    if not dev_id.startswith("emulator-"):
        return dev_id
    if dev_id not in _KEY_BY_INSTANCE:
        from pro_launch.runtime import device_boot
        _KEY_BY_INSTANCE[dev_id] = device_boot.emulator_avd_name(dev_id) or dev_id
    return _KEY_BY_INSTANCE[dev_id]


def current_host() -> dict | None:
    if "value" not in _CURRENT_HOST:
        _CURRENT_HOST["value"] = agent_hosts.find_agent_host()
    return _CURRENT_HOST["value"]


def owner_identity_strength() -> str:
    """strong: distinguishable by session id or host pid · weak: neither, so all sessions look the same."""
    return "weak" if session_identity() == ANONYMOUS_SESSION and not current_host() else "strong"


class _HostProbe:
    """Host liveness for several leases — asked once per pid (full ps listing takes 0.2-0.5 s, so not used)."""

    def __init__(self):
        self._alive_by_pid: dict[int, bool | None] = {}

    def is_alive(self, host: dict | None) -> bool | None:
        if not host or not host.get("pid"):
            return None
        pid = host["pid"]
        if pid not in self._alive_by_pid:
            self._alive_by_pid[pid] = agent_hosts.is_host_alive(host)
        return self._alive_by_pid[pid]


def is_lease_live(lease: dict, now: float | None = None, probe: _HostProbe | None = None) -> bool:
    """False if the host is dead, otherwise True only when the last use is within the idle limit."""
    if (probe or _HostProbe()).is_alive(lease.get("host")) is False:
        return False
    last_used = lease.get("last_used") or lease.get("acquired_at") or 0
    return ((now or time.time()) - float(last_used)) < lease_idle_seconds()


def is_own_lease(lease: dict) -> bool:
    """Is this session's lease. If the session id is anonymous, the host pid must match too."""
    if lease.get("session") != session_identity():
        return False
    if session_identity() != ANONYMOUS_SESSION:
        return True
    host, mine = lease.get("host") or {}, current_host() or {}
    return host.get("pid") == mine.get("pid")


def _is_recordable(dev_id: str | None) -> bool:
    return bool(dev_id) and dev_id not in UNNAMED_DEVICE_IDS


def lease_view(key: str, lease: dict, entry: dict, now: float, probe: _HostProbe) -> dict:
    """Ownership summary for responses (settings record only lists that session's keys)."""
    return {"device": lease.get("instance") or key, "key": key, "lease_id": lease.get("lease_id"),
            "session": lease.get("session"), "project_root": lease.get("project_root"),
            "purpose": lease.get("purpose"), "claimed_at": lease.get("acquired_at"),
            "last_used": lease.get("last_used"),
            "idle_seconds": round(now - float(lease.get("last_used") or now)),
            "is_live": is_lease_live(lease, now, probe), "host_alive": probe.is_alive(lease.get("host")),
            "is_booted_by_lease": bool(lease.get("is_booted_by_lease")),
            "is_auto_claimed": bool(lease.get("is_auto_claimed")),
            "changed_settings": [s.get("key") for s in entry.get("settings") or []
                                 if s.get("session") == lease.get("session")]}


def _entry_of(ledger: dict, dev_id: str) -> tuple[str, dict]:
    key = resolve_instance_key(dev_id)
    return key, ledger["devices"].get(key) or {"leases": [], "settings": []}


def device_owner(dev_id: str) -> dict | None:
    """Ownership summary of the device (live other's > live mine > most recent). None if no record."""
    key, entry = _entry_of(device_ledger.read_ledger(), dev_id)
    if not entry["leases"]:
        return None
    now, probe = time.time(), _HostProbe()
    views = [lease_view(key, lease, entry, now, probe) for lease in entry["leases"]]
    owned = [is_own_lease(lease) for lease in entry["leases"]]
    ranked = sorted(zip(views, owned), key=lambda pair: (pair[0]["is_live"], not pair[1], pair[0]["last_used"] or 0),
                    reverse=True)
    return ranked[0][0]


def owners_by_device() -> dict[str, dict]:
    """Live ownerships only > {running id and ledger key: ownership summary} (for device list · devices)."""
    ledger, now, probe = device_ledger.read_ledger(), time.time(), _HostProbe()
    owners: dict[str, dict] = {}
    for key, entry in ledger["devices"].items():
        for lease in entry["leases"]:
            view = lease_view(key, lease, entry, now, probe)
            if view["is_live"]:
                owners.setdefault(view["device"], view)
                owners.setdefault(key, view)
    return owners


def check_device_owner(dev_id: str | None) -> dict | None:
    """Warning dict if the device is held by another live lease, otherwise None."""
    if not _is_recordable(dev_id):
        return None
    key, entry = _entry_of(device_ledger.read_ledger(), dev_id)
    now, probe = time.time(), _HostProbe()
    for lease in entry["leases"]:
        if is_own_lease(lease) or not is_lease_live(lease, now, probe):
            continue
        view = lease_view(key, lease, entry, now, probe)
        purpose = f", {view['purpose']}" if view["purpose"] else ""
        return {"code": "device_owned_by_other", **view,
                "message": (f"device is used by another session ({view['session']}, {view['project_root']}{purpose}) "
                            f"(last used {view['idle_seconds']}s ago)"),
                "next": "this may overwrite that session's work — ask the user or use another device (device list shows the owner)"}
    return None


def owner_warning_fields(dev_id: str | None) -> dict:
    """Warning field to attach to action responses — empty dict if none."""
    warning = check_device_owner(dev_id)
    return {"device_owned_by_other": warning} if warning else {}


def _new_lease(instance: str, project_root: str | None, purpose: str | None, is_booted_by_lease: bool,
               is_auto_claimed: bool, backend: str | None, now: float) -> dict:
    return {"lease_id": uuid.uuid4().hex[:12], "session": session_identity(), "host": current_host(),
            "project_root": project_root, "purpose": purpose, "instance": instance, "backend": backend,
            "acquired_at": now, "last_used": now, "is_booted_by_lease": is_booted_by_lease,
            "is_auto_claimed": is_auto_claimed}


def claim_device(dev_id: str, project_root: str | None, is_auto_claimed: bool = False,
                 purpose: str | None = None, is_booted_by_lease: bool = False, backend: str | None = None,
                 is_free_required: bool = False) -> dict | None:
    """This session takes it > {owner, previous_owner, lease}. Another's lease on the same running instance is taken over.

    Settings records of a taken-over lease carry over to this session — so values to restore are not lost.
    is_free_required: recheck live leases of others inside the lock; if any, do not take it and return None (concurrent acquire race).
    Otherwise the caller first decides via check_device_owner whether taking over another's live ownership is allowed.
    """
    now = time.time()
    key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> dict | None:
        entry = ledger["devices"].setdefault(key, {"leases": [], "settings": []})
        probe = _HostProbe()
        same_instance = [lease for lease in entry["leases"] if (lease.get("instance") or key) == dev_id]
        own = next((lease for lease in same_instance if is_own_lease(lease)), None)
        others = [lease for lease in same_instance if lease is not own]
        if is_free_required and any(is_lease_live(lease, now, probe) for lease in others):
            return None
        previous = max(others, key=lambda lease: lease.get("last_used") or 0) if others else None
        previous_view = lease_view(key, previous, entry, now, probe) if previous else None
        for lease in others:
            entry["leases"].remove(lease)
            for setting in entry["settings"]:
                if setting.get("session") == lease.get("session"):
                    setting["session"] = session_identity()
        if own is None:
            own = _new_lease(dev_id, project_root, purpose, is_booted_by_lease, is_auto_claimed, backend, now)
            entry["leases"].append(own)
        else:
            own["last_used"] = now
            own["backend"] = backend or own.get("backend")
            own["project_root"] = project_root or own.get("project_root")
            own["purpose"] = purpose or own.get("purpose")
            own["is_booted_by_lease"] = bool(own.get("is_booted_by_lease") or is_booted_by_lease)
            # Any explicit claim at all means it is not auto-ownership
            own["is_auto_claimed"] = bool(own.get("is_auto_claimed")) and is_auto_claimed
        return {"owner": lease_view(key, own, entry, now, probe), "previous_owner": previous_view, "lease": dict(own)}

    return device_ledger.update_ledger(mutate)


def touch_device(dev_id: str | None, project_root: str | None) -> None:
    """Update last use of the touched device. If ownerless or released, this session takes it automatically. Others' live ownership is untouched."""
    if not _is_recordable(dev_id) or check_device_owner(dev_id):
        return
    try:
        claim_device(dev_id, project_root, is_auto_claimed=True)
    except (OSError, device_ledger.LedgerBusyError):
        pass   # a record failure does not change the action result


def release_device(dev_id: str, lease_id: str | None = None) -> dict | None:
    """Remove the lease and return settings to restore (that session's, latest change first). None if no record.

    Lease chosen: lease_id > this session's > most recent. remaining_live_leases in the response tells whether to shut down.
    """
    def mutate(ledger: dict) -> dict | None:
        key, _ = _entry_of(ledger, dev_id)
        entry = ledger["devices"].get(key)
        if not entry or not entry["leases"]:
            return None
        leases = entry["leases"]
        chosen = (next((lease for lease in leases if lease.get("lease_id") == lease_id), None) if lease_id
                  else next((lease for lease in leases if is_own_lease(lease)), None)
                  or max(leases, key=lambda lease: lease.get("last_used") or 0))
        if chosen is None:
            return None
        now, probe = time.time(), _HostProbe()
        view = lease_view(key, chosen, entry, now, probe)
        leases.remove(chosen)
        settings = [s for s in entry["settings"] if s.get("session") == chosen.get("session")]
        entry["settings"] = [s for s in entry["settings"] if s not in settings]
        remaining = sum(1 for lease in leases if is_lease_live(lease, now, probe))
        return {"owner": view, "lease": chosen, "settings": list(reversed(settings)),
                "remaining_live_leases": remaining}

    return device_ledger.update_ledger(mutate)


def leases_of_session(session: str) -> list[tuple[str, dict]]:
    """All leases of that session > [(ledger key, lease)] (for returning on session end)."""
    ledger = device_ledger.read_ledger()
    return [(key, lease) for key, entry in ledger["devices"].items() for lease in entry["leases"]
            if lease.get("session") == session]


def record_device_setting(dev_id: str, key: str, before, restore_commands: list[list[str]],
                          project_root: str | None = None) -> None:
    """Record the value before changing a device-wide setting (first value per key only — overwriting with an intermediate value loses the original).

    key examples: `appearance` · `locale:system` · `locale:app:<package>` · `ime`.
    restore_commands: argv list of commands that restore it (run in order). Used by device release · --restore.
    """
    if not _is_recordable(dev_id):
        return
    touch_device(dev_id, project_root)
    device_key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> None:
        entry = ledger["devices"].setdefault(device_key, {"leases": [], "settings": []})
        if any(s.get("key") == key for s in entry["settings"]):
            return
        entry["settings"].append({"key": key, "before": before, "restore_commands": restore_commands,
                                  "changed_at": time.time(), "session": session_identity()})

    device_ledger.update_ledger(mutate)


def pop_device_setting(dev_id: str, key: str) -> dict | None:
    """Take out one recorded setting (--restore). Looked up by device regardless of which session recorded it."""
    def mutate(ledger: dict) -> dict | None:
        device_key, _ = _entry_of(ledger, dev_id)
        entry = ledger["devices"].get(device_key)
        if not entry:
            return None
        found = next((s for s in entry["settings"] if s.get("key") == key), None)
        if found is not None:
            entry["settings"].remove(found)
        return found

    return device_ledger.update_ledger(mutate)


def set_pool_booted(dev_id: str, is_booted: bool) -> None:
    """Device mark set by acquire (so it is not treated as a human-used device even when on) · cleared when turned off."""
    key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> None:
        entry = ledger["devices"].setdefault(key, {"leases": [], "settings": []})
        if is_booted:
            entry["pool_booted_at"] = time.time()
        else:
            entry.pop("pool_booted_at", None)

    device_ledger.update_ledger(mutate)


def record_wait(wait_key: str) -> float:
    """Update the wait record > seconds since waiting first began (wait combined across calls)."""
    now = time.time()

    def mutate(ledger: dict) -> float:
        record = ledger["waits"].setdefault(wait_key, {"started_at": now})
        record["updated_at"] = now
        return now - float(record["started_at"])

    return device_ledger.update_ledger(mutate)


def waited_seconds(wait_key: str) -> float:
    record = device_ledger.read_ledger()["waits"].get(wait_key)
    return time.time() - float(record["started_at"]) if record else 0.0


def clear_wait(wait_key: str) -> None:
    device_ledger.update_ledger(lambda ledger: ledger["waits"].pop(wait_key, None))


def pop_settings_of_session(dev_id: str, session: str) -> list[dict]:
    """Take out settings that session recorded (latest change first) — restored before taking over on reclaim."""
    key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> list[dict]:
        entry = ledger["devices"].get(key)
        if not entry:
            return []
        taken = [s for s in entry["settings"] if s.get("session") == session]
        entry["settings"] = [s for s in entry["settings"] if s not in taken]
        return list(reversed(taken))

    return device_ledger.update_ledger(mutate)


def keep_settings_for_this_session(dev_id: str, settings: list[dict]) -> None:
    """Put settings that failed to restore back into this session's record (the next release retries)."""
    key = resolve_instance_key(dev_id)

    def mutate(ledger: dict) -> None:
        entry = ledger["devices"].setdefault(key, {"leases": [], "settings": []})
        entry["settings"].extend({**s, "session": session_identity()} for s in settings)

    device_ledger.update_ledger(mutate)
