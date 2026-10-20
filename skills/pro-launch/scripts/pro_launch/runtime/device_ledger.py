"""기기 원장 파일 `{base}/launch/_machine/device-claims.json`: 읽기(schema 1 받아들임) · 잠금 > 읽기 > 고치기 > 저장 (#953).

모양: {"schema": 2, "devices": {키: {leases, settings, pool_booted_at}}, "waits": {대기 키: {started_at, updated_at}}}
키: iOS UDID · Android AVD 이름 · 실기기 시리얼 (Android 시리얼은 lease 의 instance). 저장은 임시 파일 > 바꿔치기.
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
# 잠금 대기 상한 (초) — 넘으면 LedgerBusyError
LOCK_TIMEOUT_SECONDS = 10.0
LOCK_RETRY_SECONDS = 0.05
# 대기 기록 보관 (초) — 이보다 오래된 것은 저장할 때 버린다 (1시간)
WAIT_RECORD_KEEP_SECONDS = 60 * 60

ResultType = TypeVar("ResultType")


class LedgerBusyError(RuntimeError):
    """잠금을 상한 안에 얻지 못했다 — 조작하지 않고 실패로 알린다 (code: ledger_busy)."""


def ledger_path() -> Path:
    return base_dir() / "launch" / MACHINE_BUCKET / LEDGER_FILE_NAME


def empty_ledger() -> dict:
    return {"schema": LEDGER_SCHEMA, "devices": {}, "waits": {}}


def _from_schema1(claims: dict) -> dict:
    """schema 1 {claims: {id: claim}} > 기기마다 lease 1개 (호스트 기록 없음)."""
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
    """원장 > schema 2 dict. 없거나 깨진 파일은 빈 원장 (다음 저장이 고친다)."""
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
    """빈 기기 항목 · 오래된 대기 기록을 뺀다."""
    devices = {k: v for k, v in ledger["devices"].items()
               if v.get("leases") or v.get("settings") or v.get("pool_booted_at")}
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
    """원장 잠금 구간. 상한 안에 못 얻으면 LedgerBusyError."""
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
    """잠금 > 읽기 > mutate(원장 dict 를 고친다) > 정리 > 저장. mutate 의 반환값을 돌려준다."""
    with locked_ledger():
        ledger = read_ledger()
        result = mutate(ledger)
        _write(_prune(ledger, time.time()))
    return result
