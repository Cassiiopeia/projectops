"""Records when pro-launch started Maestro · counts Maestro runs outside it (#863) · machine-wide lock (#922).

Maestro leaves ~/.maestro/tests/<yyyy-MM-dd_HHmmss>/ per run. Folders whose time does not match the intervals
pro-launch recorded = direct runs that bypassed launch_cli (methods learned there are not kept in memory).
Counting looks only at folder names and times — maestro.log may hold secret input values in plaintext.
One exception: the last error line of a failed response is read only from **the folder of the run this call started**
(flows with secret input redirect logs to a temp folder so nothing stays here · inputText lines are skipped).

Record: {PROJECTOPS_HOME}/launch/maestro_runs.json — [[start, end], ...] latest RUNS_KEEP entries (shared across devices)
Lock: {PROJECTOPS_HOME}/launch/maestro.lock — {"pid", "acquired_at"}. Two Maestros at once drop the iOS driver
connection (observed: Android·iOS concurrent runs > ConnectException) — one at a time per machine.
Top level imports only the standard library — the relay (standalone) imports it via maestro_session.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import re
import subprocess
import time
from pathlib import Path

RUNS_FILE_NAME = "maestro_runs.json"
RUNS_KEEP = 200
# Tolerance between folder-name time (second precision · JVM startup lag) <-> recorded interval
MATCH_SLACK_SECONDS = 15
FOLDER_NAME_FORMAT = "%Y-%m-%d_%H%M%S"
LOCK_FILE_NAME = "maestro.lock"
# Max wait for a lock held by another call (s) — past it, proceed without the lock and just report (per-call 90 s timeout + margin)
LOCK_WAIT_SECONDS = 150
LOCK_POLL_SECONDS = 0.5
# A lock older than this is abandoned even if its holder is alive (s)
LOCK_STALE_SECONDS = 600
# How long a freshly created, still-empty lock file counts as live (s)
LOCK_FRESH_EMPTY_SECONDS = 5
# Last error line: phrases to find · lines to skip (may carry input values) · max characters · tail bytes read
ERROR_LINE_MARKERS = ("Exception", "Error", "FAILED", "[Failed]", "not found", "timed out")
ERROR_LINE_EXCLUDED = ("inputText", "InputText")
ERROR_LINE_MAXIMUM_CHARS = 300
LOG_TAIL_BYTES = 65536
# maestro.log line prefix: '10:53:18.395 [ INFO] '
LOG_LINE_PREFIX = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d+\s+\[\s*(\w+)\]\s*")

# This process's last run interval · total lock wait (launch_cli is a new process per call)
LAST_RUN: dict = {}
LOCK_WAIT: dict = {"waited_seconds": 0.0, "holder_pid": None, "is_timed_out": False}
_LOCK_DEPTH = [0]


def maestro_tests_folder() -> Path:
    """Maestro's default log location (relative to HOME at call time)."""
    return Path.home() / ".maestro" / "tests"


def runs_file() -> Path:
    from common.state import base_dir   # the relay is standalone, so import only here
    return base_dir() / "launch" / RUNS_FILE_NAME


def lock_file() -> Path:
    from common.state import base_dir
    return base_dir() / "launch" / LOCK_FILE_NAME


def read_runs() -> list[list[float]]:
    try:
        rows = json.loads(runs_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [row for row in rows if isinstance(row, list) and len(row) == 2] if isinstance(rows, list) else []


def record_run(started_at: float, ended_at: float) -> None:
    """Append one interval. A record failure does not spoil the main command."""
    LAST_RUN.update(started_at=started_at, ended_at=ended_at)
    try:
        path = runs_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([*read_runs(), [started_at, ended_at]][-RUNS_KEEP:]), encoding="utf-8")
    except Exception:   # noqa: BLE001 — the record is auxiliary
        pass


@contextlib.contextmanager
def recording():
    """Record that Maestro runs during this block (success·failure·exception alike)."""
    started_at = time.time()
    try:
        yield
    finally:
        record_run(started_at, time.time())


def run_recorded(command: list[str], **options) -> subprocess.CompletedProcess:
    """Same as subprocess.run + machine-wide lock + run-interval record. On timeout, cleans up orphan drivers this run left."""
    started_at = time.time()
    with start_lock(), recording():
        try:
            return subprocess.run(command, **options)
        except subprocess.TimeoutExpired:
            # A timeout kills only the direct child (JVM) — the xcodebuild driver below it is left orphaned
            import maestro_drivers
            device = command[command.index("--device") + 1] if "--device" in command[:-1] else None
            maestro_drivers.clean_after_timeout(device, time.time() - started_at)
            raise


# ── Machine-wide lock ───────────────────────────────────────────────────────

@contextlib.contextmanager
def start_lock(wait_seconds: float = LOCK_WAIT_SECONDS):
    """Lock around starting Maestro: acquire > wait while the holder is alive (capped) > block > release only our own.

    Nested acquisition in the same process is fine. Wait time accumulates in LOCK_WAIT (maestro_lock in the response).
    """
    if _LOCK_DEPTH[0]:
        _LOCK_DEPTH[0] += 1
        try:
            yield
        finally:
            _LOCK_DEPTH[0] -= 1
        return
    started = time.monotonic()
    is_held, holder_pid = _try_acquire()
    while not is_held and holder_pid is not None and time.monotonic() - started < wait_seconds:
        time.sleep(LOCK_POLL_SECONDS)
        is_held, holder_pid = _try_acquire()
    waited_seconds = time.monotonic() - started
    if waited_seconds >= LOCK_POLL_SECONDS:
        LOCK_WAIT.update(waited_seconds=round(LOCK_WAIT["waited_seconds"] + waited_seconds, 1),
                         holder_pid=holder_pid, is_timed_out=LOCK_WAIT["is_timed_out"] or not is_held)
    _LOCK_DEPTH[0] = 1
    try:
        yield
    finally:
        _LOCK_DEPTH[0] = 0
        if is_held:
            _release()


def _try_acquire() -> tuple[bool, int | None]:
    """> (acquired, holder pid). Abandoned locks (holder dead · too old) are cleared and retried. If the spot is unusable (False, None) — no lock."""
    from common.proc import pid_alive
    path = lock_file()
    for _ in range(2):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            holder = _read_lock(path)
            holder_pid = holder.get("pid")
            is_abandoned = (not holder_pid or holder_pid == os.getpid()
                            or (holder_pid > 0 and not pid_alive(holder_pid))
                            or time.time() - float(holder.get("acquired_at") or 0) > LOCK_STALE_SECONDS)
            if not is_abandoned:
                return False, int(holder_pid)
            with contextlib.suppress(OSError):
                path.unlink()
            continue
        except OSError:
            return False, None
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "acquired_at": time.time()}, handle)
        return True, None
    return False, None


def _read_lock(path: Path) -> dict:
    """Lock contents. A freshly created empty lock has an unknown holder (pid -1) and counts as live."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    with contextlib.suppress(OSError):
        if time.time() - path.stat().st_mtime < LOCK_FRESH_EMPTY_SECONDS:
            return {"pid": -1, "acquired_at": time.time()}
    return {}


def _release() -> None:
    """Remove only the lock we hold."""
    path = lock_file()
    if _read_lock(path).get("pid") == os.getpid():
        with contextlib.suppress(OSError):
            path.unlink()


def lock_wait_report() -> dict:
    """Lock wait to attach to the response: {"maestro_lock": {waited_seconds, holder_pid, is_timed_out}}. {} if it never waited."""
    if not LOCK_WAIT["waited_seconds"]:
        return {}
    return {"maestro_lock": {key: value for key, value in LOCK_WAIT.items() if value not in (None, False)}}


# ── Last error line ────────────────────────────────────────────────────────

def last_error_line() -> str | None:
    """Last error line of maestro.log left by this process's last run (ERROR level first). None if none."""
    if not LAST_RUN:
        return None
    folder = _own_run_folder(LAST_RUN["started_at"], LAST_RUN["ended_at"])
    if folder is None:
        return None
    try:
        with open(folder / "maestro.log", "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - LOG_TAIL_BYTES))
            lines = handle.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    candidates = [line for line in lines if any(marker in line for marker in ERROR_LINE_MARKERS)
                  and not any(excluded in line for excluded in ERROR_LINE_EXCLUDED)]
    error_level = [line for line in candidates
                   if (LOG_LINE_PREFIX.match(line) and LOG_LINE_PREFIX.match(line).group(1) == "ERROR")]
    chosen = (error_level or candidates or [None])[-1]
    return LOG_LINE_PREFIX.sub("", chosen).strip()[:ERROR_LINE_MAXIMUM_CHARS] if chosen else None


def _own_run_folder(started_at: float, ended_at: float) -> Path | None:
    """The log folder created within the run interval that is closest to its start."""
    try:
        folders = [path for path in maestro_tests_folder().iterdir() if path.is_dir()]
    except OSError:
        return None
    inside = [(at, path) for at, path in ((folder_started_at(path), path) for path in folders)
              if at is not None and started_at - MATCH_SLACK_SECONDS <= at <= ended_at + MATCH_SLACK_SECONDS]
    return min(inside, key=lambda pair: abs(pair[0] - started_at))[1] if inside else None


# ── Counting runs from outside ───────────────────────────────────────────────────

def folder_started_at(folder: Path) -> float | None:
    """Folder name (local time) > epoch seconds. Folder mtime if the name format differs (stat only, contents not read)."""
    try:
        return dt.datetime.strptime(folder.name, FOLDER_NAME_FORMAT).timestamp()
    except ValueError:
        pass
    try:
        return folder.stat().st_mtime
    except OSError:
        return None


def count_outside_runs(window_seconds: float, tests_folder: Path | None = None, now: float | None = None) -> int:
    """Number of Maestro log folders within the last window_seconds that fall outside pro-launch run intervals."""
    now = now if now is not None else time.time()
    tests_folder = tests_folder or maestro_tests_folder()
    try:
        folders = [path for path in tests_folder.iterdir() if path.is_dir()]
    except OSError:
        return 0
    runs = read_runs()
    if not runs:
        return 0                                    # without records, inside and outside cannot be told apart
    # Count only folders after recording began — earlier runs would all count as 'outside'
    counted_since = max(now - window_seconds, min(start for start, _ in runs) - MATCH_SLACK_SECONDS)
    count = 0
    for folder in folders:
        started_at = folder_started_at(folder)
        if started_at is None or started_at < counted_since:
            continue
        is_inside_launch = any(start - MATCH_SLACK_SECONDS <= started_at <= end + MATCH_SLACK_SECONDS
                               for start, end in runs)
        count += 0 if is_inside_launch else 1
    return count
