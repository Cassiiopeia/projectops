"""pro-launch 가 Maestro 를 띄운 시각 기록 · 그 밖에서 돈 Maestro 실행 세기 (#863).

Maestro 는 실행마다 ~/.maestro/tests/<yyyy-MM-dd_HHmmss>/ 를 남긴다. pro-launch 가 띄운 구간 기록과
시각이 안 맞는 폴더 = launch_cli 를 거치지 않은 직접 실행 (그 사이 알게 된 방식은 기억에 안 남는다).
폴더 내용은 읽지 않는다 — maestro.log 에 비밀 입력값이 평문으로 남을 수 있다. 이름 · 시각만 본다.

기록: {PROJECTOPS_HOME}/launch/maestro_runs.json — [[시작, 끝], ...] 최근 RUNS_KEEP 건 (기기 공용)
top-level 에서는 표준 라이브러리만 들인다 — 중계(standalone)가 maestro_session 을 거쳐 import 한다.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

RUNS_FILE_NAME = "maestro_runs.json"
RUNS_KEEP = 200
# 폴더 이름 시각(초 단위 · JVM 기동 지연) <-> 기록 구간 허용 오차
MATCH_SLACK_SECONDS = 15
FOLDER_NAME_FORMAT = "%Y-%m-%d_%H%M%S"


def maestro_tests_folder() -> Path:
    """Maestro 기본 기록 자리 (부를 때 HOME 기준)."""
    return Path.home() / ".maestro" / "tests"


def runs_file() -> Path:
    from common.state import base_dir   # 중계는 standalone 이라 여기서만 들인다
    return base_dir() / "launch" / RUNS_FILE_NAME


def read_runs() -> list[list[float]]:
    try:
        rows = json.loads(runs_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [row for row in rows if isinstance(row, list) and len(row) == 2] if isinstance(rows, list) else []


def record_run(started_at: float, ended_at: float) -> None:
    """구간 하나 덧붙이기. 기록 실패는 본 명령을 망치지 않는다."""
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
    """subprocess.run 과 같다 + 실행 구간 기록."""
    with recording():
        return subprocess.run(command, **options)


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
