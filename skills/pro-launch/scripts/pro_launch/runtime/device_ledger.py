"""Device ledger file `{base}/launch/_machine/device-claims.json`: read (accepts schema 1) · lock > read > modify > save (#953).

Shape: {"schema": 2, "devices": {key: {leases, settings, pool_booted_at, marks, origin, temporary}}, "waits": {wait key: {started_at, updated_at}}}
Key: iOS UDID · Android AVD name · physical device serial (the Android serial is the lease's instance). Saved via temp file > swap.
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Callable, TypeVar

from common.state import MACHINE_BUCKET, base_dir

from pro_launch.runtime import procs

LEDGER_FILE_NAME = "device-claims.json"
LEDGER_SCHEMA = 2
# Lock wait cap (s) — LedgerBusyError beyond it
LOCK_TIMEOUT_SECONDS = 10.0
LOCK_RETRY_SECONDS = 0.05
# Wait record retention (s) — older ones are dropped on save (1 hour)
WAIT_RECORD_KEEP_SECONDS = 60 * 60

# A device entry is kept if any of these exist (lease · settings record · powered-on mark · prepared state · origin · temporary device record)
KEPT_ENTRY_FIELDS = ("leases", "settings", "pool_booted_at", "marks", "origin", "temporary")

ResultType = TypeVar("ResultType")


class LedgerBusyError(RuntimeError):
    """Could not get the lock within the cap — report failure without acting (code: ledger_busy)."""


def ledger_path() -> Path:
    return base_dir() / "launch" / MACHINE_BUCKET / LEDGER_FILE_NAME


def empty_ledger() -> dict:
    return {"schema": LEDGER_SCHEMA, "devices": {}, "waits": {}}


def _from_schema1(claims: dict) -> dict:
    """schema 1 {claims: {id: claim}} > one lease per device (no host record)."""
    devices = {}
    for key, claim in claims.items():
        if not isinstance(claim, dict):
            continue
        lease = {"lease_id": f"legacy-{key}", "session": claim.get("session"), "host": None,
                 "project_root": claim.get("project_root"), "purpose": None, "instance": key,
                 "acquired_at": claim.get("claimed_at"), "last_used": claim.get("last_used") or claim.get("claimed_at"),
                 "is_booted_by_lease": False, "is_auto_claimed": bool(claim.get("is_auto_claimed"))}
        settings = [{**s, "session": claim.get("session")} for s in claim.get("settings") or [] if isinstance(s, dict)]
        devices[key] = {"leases": [lease], "settings": settings}
    return {**empty_ledger(), "devices": devices}


def read_ledger() -> dict:
    """Ledger > schema 2 dict. Missing or broken files give an empty ledger (the next save fixes it)."""
    try:
        data = json.loads(ledger_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_ledger()
    if not isinstance(data, dict):
        return empty_ledger()
    if "claims" in data and "devices" not in data:
        return _from_schema1(data.get("claims") or {})
    devices = {k: v for k, v in (data.get("devices") or {}).items() if isinstance(v, dict)}
    for entry in devices.values():
        entry["leases"] = [lease for lease in entry.get("leases") or [] if isinstance(lease, dict)]
        entry["settings"] = [s for s in entry.get("settings") or [] if isinstance(s, dict)]
    waits = {k: v for k, v in (data.get("waits") or {}).items() if isinstance(v, dict)}
    return {"schema": LEDGER_SCHEMA, "devices": devices, "waits": waits}


def _prune(ledger: dict, now: float) -> dict:
    """Drop empty device entries · stale wait records."""
    devices = {k: v for k, v in ledger["devices"].items()
               if any(v.get(field) for field in KEPT_ENTRY_FIELDS)}
    waits = {k: v for k, v in ledger.get("waits", {}).items()
             if now - float(v.get("updated_at") or 0) < WAIT_RECORD_KEEP_SECONDS}
    return {"schema": LEDGER_SCHEMA, "devices": devices, "waits": waits}


def _write(ledger: dict) -> None:
    path = ledger_path()
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


@contextlib.contextmanager
def locked_ledger(timeout_seconds: float = LOCK_TIMEOUT_SECONDS):
    """Ledger lock section. LedgerBusyError if not acquired within the cap."""
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(f"{path.name}.lock"), "a+b") as handle:
        deadline = time.monotonic() + timeout_seconds
        while not procs.try_lock_file(handle):
            if time.monotonic() >= deadline:
                raise LedgerBusyError(f"device ledger is locked by another process ({timeout_seconds:.0f}s)")
            time.sleep(LOCK_RETRY_SECONDS)
        try:
            yield
        finally:
            procs.unlock_file(handle)


def update_ledger(mutate: Callable[[dict], ResultType]) -> ResultType:
    """lock > read > mutate (modifies the ledger dict) > tidy > save. Returns mutate's return value."""
    with locked_ledger():
        ledger = read_ledger()
        result = mutate(ledger)
        _write(_prune(ledger, time.time()))
    return result
