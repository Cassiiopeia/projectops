"""데스크톱 입력 세션 · ref 스냅샷 기록 (#985).

키보드·마우스는 컴퓨터에 하나뿐이라 입력 세션도 **컴퓨터 전체에 하나**다.
`{base}/launch/_machine/desktop/session.json` 에 쥔 세션을 적고, 기기 원장과 같은 파일 잠금으로 고친다.

ref 는 세션마다 따로 적는다 (`snapshot-<세션>.json`). 다른 세션의 find 결과로 누르지 않게.
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

# 입력이 이만큼(초) 없으면 세션이 풀린다 — 끝내지 않고 떠난 세션이 마우스를 계속 쥐지 않게
SESSION_IDLE_SECONDS = 10 * 60
LOCK_TIMEOUT_SECONDS = 10.0
LOCK_RETRY_SECONDS = 0.05


class DesktopLockBusy(RuntimeError):
    """상태 파일 잠금을 상한 안에 얻지 못했다 (code: desktop_state_busy)."""


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


# ── 입력 세션 ────────────────────────────────────────────────────────────

def is_live(record: dict, now: float) -> bool:
    """기록된 세션이 아직 유효한가 — 마지막 입력 뒤 SESSION_IDLE_SECONDS 안."""
    return bool(record.get("session")) and now - float(record.get("last_used") or 0) < SESSION_IDLE_SECONDS


def current_holder(now: float | None = None) -> dict | None:
    """지금 입력 세션을 쥔 기록. 없거나 만료면 None."""
    record = _read(state_dir() / "session.json")
    return record if is_live(record, now or time.time()) else None


def start_session(purpose: str | None = None, now: float | None = None) -> tuple[bool, dict]:
    """(얻었나, 기록). 다른 세션이 쥐고 있으면 (False, 그 기록). 같은 세션이면 갱신한다."""
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
    """이 세션이 쥔 경우에만 푼다. 풀었으면 True."""
    me = session_identity()
    with _locked():
        path = state_dir() / "session.json"
        if _read(path).get("session") != me:
            return False
        path.unlink(missing_ok=True)
        return True


def my_session(now: float | None = None) -> dict | None:
    """이 세션이 쥔 유효한 기록. 아니면 None."""
    record = current_holder(now)
    return record if record and record.get("session") == session_identity() else None


def touch_session(**changes) -> None:
    """마지막 입력 시각·커서 위치·일시정지를 고친다. 이 세션 기록일 때만."""
    me = session_identity()
    with _locked():
        path = state_dir() / "session.json"
        record = _read(path)
        if record.get("session") != me:
            return
        record.update(changes)
        record["last_used"] = time.time()
        _write(path, record)


# ── ref 스냅샷 ───────────────────────────────────────────────────────────

def _snapshot_path() -> Path:
    key = hashlib.sha1(session_identity().encode("utf-8")).hexdigest()[:12]
    return state_dir() / f"snapshot-{key}.json"


def save_snapshot(window: dict, nodes: list[dict]) -> None:
    """tree·find 가 보여 준 ref 를 적는다. click --ref 가 이 기록으로 요소를 다시 찾는다."""
    _write(_snapshot_path(), {"taken_at": time.time(), "window": window, "nodes": nodes})


def load_snapshot() -> dict:
    return _read(_snapshot_path())
