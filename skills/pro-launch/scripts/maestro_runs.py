"""pro-launch 가 Maestro 를 띄운 시각 기록 · 그 밖에서 돈 Maestro 실행 세기 (#863) · 기계 단위 잠금 (#922).

Maestro 는 실행마다 ~/.maestro/tests/<yyyy-MM-dd_HHmmss>/ 를 남긴다. pro-launch 가 띄운 구간 기록과
시각이 안 맞는 폴더 = launch_cli 를 거치지 않은 직접 실행 (그 사이 알게 된 방식은 기억에 안 남는다).
세기는 폴더 이름 · 시각만 본다 — maestro.log 에 비밀 입력값이 평문으로 남을 수 있다.
예외 하나: 실패 응답의 마지막 오류 줄은 **이번 호출이 띄운 실행의 폴더**에서만 읽는다
(비밀 입력 flow 는 기록을 임시 폴더로 돌려 여기 안 남는다 · inputText 줄은 건너뛴다).

기록: {PROJECTOPS_HOME}/launch/maestro_runs.json — [[시작, 끝], ...] 최근 RUNS_KEEP 건 (기기 공용)
잠금: {PROJECTOPS_HOME}/launch/maestro.lock — {"pid", "acquired_at"}. Maestro 둘이 동시에 뜨면 iOS 드라이버
연결이 끊긴다 (실측: Android·iOS 동시 실행 > ConnectException) — 기계 하나에 하나씩 띄운다.
top-level 에서는 표준 라이브러리만 들인다 — 중계(standalone)가 maestro_session 을 거쳐 import 한다.
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
# 폴더 이름 시각(초 단위 · JVM 기동 지연) <-> 기록 구간 허용 오차
MATCH_SLACK_SECONDS = 15
FOLDER_NAME_FORMAT = "%Y-%m-%d_%H%M%S"
LOCK_FILE_NAME = "maestro.lock"
# 다른 호출이 쥔 잠금 최대 대기 (초) — 넘으면 잠금 없이 진행하고 보고만 (호출당 시간 초과 90초 + 여유)
LOCK_WAIT_SECONDS = 150
LOCK_POLL_SECONDS = 0.5
# 쥔 프로세스가 살아 있어도 이보다 오래된 잠금은 버려진 것 (초)
LOCK_STALE_SECONDS = 600
# 막 만들어 아직 빈 잠금 파일을 살아 있는 것으로 보는 시간 (초)
LOCK_FRESH_EMPTY_SECONDS = 5
# 마지막 오류 줄: 찾는 문구 · 건너뛰는 줄(입력값이 실릴 수 있다) · 최대 글자 · 읽는 끝부분 (바이트)
ERROR_LINE_MARKERS = ("Exception", "Error", "FAILED", "[Failed]", "not found", "timed out")
ERROR_LINE_EXCLUDED = ("inputText", "InputText")
ERROR_LINE_MAXIMUM_CHARS = 300
LOG_TAIL_BYTES = 65536
# maestro.log 줄 머리: '10:53:18.395 [ INFO] '
LOG_LINE_PREFIX = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d+\s+\[\s*(\w+)\]\s*")

# 이 프로세스의 마지막 실행 구간 · 잠금 대기 합계 (launch_cli 는 호출마다 새 프로세스)
LAST_RUN: dict = {}
LOCK_WAIT: dict = {"waited_seconds": 0.0, "holder_pid": None, "is_timed_out": False}
_LOCK_DEPTH = [0]


def maestro_tests_folder() -> Path:
    """Maestro 기본 기록 자리 (부를 때 HOME 기준)."""
    return Path.home() / ".maestro" / "tests"


def runs_file() -> Path:
    from common.state import base_dir   # 중계는 standalone 이라 여기서만 들인다
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
    """구간 하나 덧붙이기. 기록 실패는 본 명령을 망치지 않는다."""
    LAST_RUN.update(started_at=started_at, ended_at=ended_at)
    try:
        path = runs_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([*read_runs(), [started_at, ended_at]][-RUNS_KEEP:]), encoding="utf-8")
    except Exception:   # noqa: BLE001 — 기록은 보조다
        pass


@contextlib.contextmanager
def recording():
    """이 블록 동안 Maestro 가 돈다고 기록 (성공·실패·예외 공통)."""
    started_at = time.time()
    try:
        yield
    finally:
        record_run(started_at, time.time())


def run_recorded(command: list[str], **options) -> subprocess.CompletedProcess:
    """subprocess.run 과 같다 + 기계 단위 잠금 + 실행 구간 기록. 시간 초과면 이번 실행이 남긴 고아 드라이버 정리."""
    started_at = time.time()
    with start_lock(), recording():
        try:
            return subprocess.run(command, **options)
        except subprocess.TimeoutExpired:
            # 시간 초과는 직계(JVM)만 끝낸다 — 그 아래 xcodebuild 드라이버가 고아로 남는다
            import maestro_drivers
            device = command[command.index("--device") + 1] if "--device" in command[:-1] else None
            maestro_drivers.clean_after_timeout(device, time.time() - started_at)
            raise


# ── 기계 단위 잠금 ───────────────────────────────────────────────────────

@contextlib.contextmanager
def start_lock(wait_seconds: float = LOCK_WAIT_SECONDS):
    """Maestro 를 띄우는 구간 잠금: 잡기 > 쥔 쪽이 살아 있으면 대기(상한) > 블록 > 자기 것만 풀기.

    같은 프로세스 안에서는 겹쳐 잡아도 된다. 기다린 시간은 LOCK_WAIT 에 쌓인다 (응답의 maestro_lock).
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
    """> (잡았나, 쥔 pid). 버려진 잠금(쥔 쪽 죽음 · 너무 오래됨)은 걷고 다시. 자리를 못 쓰면 (False, None) — 잠금 없이."""
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
    """잠금 내용. 막 만들어 아직 비었으면 쥔 쪽 모름(pid -1)으로 살아 있는 것 취급."""
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
    """자기가 쥔 잠금만 지운다."""
    path = lock_file()
    if _read_lock(path).get("pid") == os.getpid():
        with contextlib.suppress(OSError):
            path.unlink()


def lock_wait_report() -> dict:
    """응답에 붙일 잠금 대기: {"maestro_lock": {waited_seconds, holder_pid, is_timed_out}}. 기다린 적 없으면 {}."""
    if not LOCK_WAIT["waited_seconds"]:
        return {}
    return {"maestro_lock": {key: value for key, value in LOCK_WAIT.items() if value not in (None, False)}}


# ── 마지막 오류 줄 ────────────────────────────────────────────────────────

def last_error_line() -> str | None:
    """이번 프로세스의 마지막 실행이 남긴 maestro.log 의 마지막 오류 줄 (ERROR 수준 우선). 없으면 None."""
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
    """실행 구간 안에서 생긴 기록 폴더 중 시작에 가장 가까운 것."""
    try:
        folders = [path for path in maestro_tests_folder().iterdir() if path.is_dir()]
    except OSError:
        return None
    inside = [(at, path) for at, path in ((folder_started_at(path), path) for path in folders)
              if at is not None and started_at - MATCH_SLACK_SECONDS <= at <= ended_at + MATCH_SLACK_SECONDS]
    return min(inside, key=lambda pair: abs(pair[0] - started_at))[1] if inside else None


# ── 밖에서 돈 실행 세기 ───────────────────────────────────────────────────

def folder_started_at(folder: Path) -> float | None:
    """폴더 이름(로컬 시각) > epoch 초. 이름 형식이 다르면 폴더 수정 시각 (stat 만, 내용은 안 읽는다)."""
    try:
        return dt.datetime.strptime(folder.name, FOLDER_NAME_FORMAT).timestamp()
    except ValueError:
        pass
    try:
        return folder.stat().st_mtime
    except OSError:
        return None


def count_outside_runs(window_seconds: float, tests_folder: Path | None = None, now: float | None = None) -> int:
    """최근 window_seconds 안의 Maestro 기록 폴더 중 pro-launch 실행 구간에 안 들어가는 개수."""
    now = now if now is not None else time.time()
    tests_folder = tests_folder or maestro_tests_folder()
    try:
        folders = [path for path in tests_folder.iterdir() if path.is_dir()]
    except OSError:
        return 0
    runs = read_runs()
    if not runs:
        return 0                                    # 기록이 없으면 안팎을 가를 수 없다
    # 기록을 남기기 시작한 뒤의 폴더만 센다 — 그 전 실행은 전부 '밖'으로 잡힌다
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
