"""Desktop input session · ref snapshot records (#985).

A computer has only one keyboard and mouse, so the input session is also **one per computer**.
The holding session is written to `{base}/launch/_machine/desktop/session.json` and updated under the same file lock as the device ledger.

refs are written per session (`snapshot-<session>.json`), so nobody presses using another session's find results.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from pathlib import Path

from common.state import MACHINE_BUCKET, base_dir

from pro_launch.runtime import procs
from pro_launch.runtime.session_identity import session_identity

# The session is released after this many seconds without input — so a session that left without ending does not keep holding the mouse
SESSION_IDLE_SECONDS = 10 * 60
LOCK_TIMEOUT_SECONDS = 10.0
LOCK_RETRY_SECONDS = 0.05


class DesktopLockBusy(RuntimeError):
    """Could not get the state file lock within the limit (code: desktop_state_busy)."""


def state_dir() -> Path:
    d = base_dir() / "launch" / MACHINE_BUCKET / "desktop"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict) -> None:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


@contextlib.contextmanager
def _locked():
    path = state_dir() / "session.lock"
    with open(path, "a+b") as handle:
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while not procs.try_lock_file(handle):
            if time.monotonic() >= deadline:
                raise DesktopLockBusy("desktop session file is locked by another process")
            time.sleep(LOCK_RETRY_SECONDS)
        try:
            yield
        finally:
            procs.unlock_file(handle)


# ── Input session ────────────────────────────────────────────────────────────

def is_live(record: dict, now: float) -> bool:
    """Is the recorded session still valid — within SESSION_IDLE_SECONDS of the last input."""
    return bool(record.get("session")) and now - float(record.get("last_used") or 0) < SESSION_IDLE_SECONDS


def current_holder(now: float | None = None) -> dict | None:
    """Record of who holds the input session now. None if none or expired."""
    record = _read(state_dir() / "session.json")
    return record if is_live(record, now or time.time()) else None


def start_session(purpose: str | None = None, now: float | None = None) -> tuple[bool, dict]:
    """(acquired, record). If another session holds it (False, its record). The same session refreshes it."""
    now = now or time.time()
    me = session_identity()
    with _locked():
        path = state_dir() / "session.json"
        record = _read(path)
        if is_live(record, now) and record["session"] != me:
            return False, record
        fresh = {"session": me, "purpose": purpose, "started_at": record.get("started_at") if
                 record.get("session") == me and is_live(record, now) else now,
                 "last_used": now, "paused": False, "last_cursor": None}
        _write(path, fresh)
        return True, fresh


def stop_session() -> bool:
    """Release only if this session holds it. True if released."""
    me = session_identity()
    with _locked():
        path = state_dir() / "session.json"
        if _read(path).get("session") != me:
            return False
        path.unlink(missing_ok=True)
        return True


def my_session(now: float | None = None) -> dict | None:
    """Valid record held by this session. Otherwise None."""
    record = current_holder(now)
    return record if record and record.get("session") == session_identity() else None


def touch_session(**changes) -> None:
    """Update last input time · cursor position · pause. Only for this session's record."""
    me = session_identity()
    with _locked():
        path = state_dir() / "session.json"
        record = _read(path)
        if record.get("session") != me:
            return
        record.update(changes)
        record["last_used"] = time.time()
        _write(path, record)


# ── ref snapshot ───────────────────────────────────────────────────────────

def _snapshot_path() -> Path:
    key = hashlib.sha1(session_identity().encode("utf-8")).hexdigest()[:12]
    return state_dir() / f"snapshot-{key}.json"


def save_snapshot(window: dict, nodes: list[dict]) -> None:
    """Write the refs tree·find showed. click --ref uses this record to find the element again."""
    _write(_snapshot_path(), {"taken_at": time.time(), "window": window, "nodes": nodes})


def load_snapshot() -> dict:
    return _read(_snapshot_path())
