"""브라우저를 띄우는 테스트의 정리 — `web close` 가 실패해도 pid 로 끝낸다 (#921).

예전 fixture 는 `web close` 만 불렀다. 그게 실패하면 부모 없는 headless Chrome 이 남고(임시 폴더는 지워져 프로필도 없다),
쌓이면 사용자의 Chrome(HTML 파일 열기)을 가로챘다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from pro_launch.runtime.procs import kill_browser, pid_alive, process_table  # noqa: E402


def recorded_browser_pid(state_dir: Path) -> int | None:
    """상태 폴더의 browser.json 에 적힌 브라우저 pid. 없으면 None"""
    try:
        return int(json.loads((Path(state_dir) / "browser.json").read_text(encoding="utf-8")).get("pid"))
    except (OSError, ValueError, TypeError):
        return None


def close_browser_for_test(run_cli, project: Path, state_dir: Path) -> None:
    """web close > 그래도 살아 있으면 pid 로 강제 종료 (성공 · 실패 공통)"""
    pid = recorded_browser_pid(state_dir)
    run_cli("web", "close", "--root", str(project))
    if pid is not None and pid_alive(pid):
        kill_browser(pid, grace=1.0)


def browser_pids_under(folder: Path) -> list[int]:
    """--user-data-dir 가 folder 아래인 Chrome 본 프로세스 pid (렌더러 · GPU 자식 제외)"""
    prefix = str(Path(folder).resolve())
    table = process_table() or []
    return [row["pid"] for row in table
            if "--remote-debugging-port=" in row["command"] and "--type=" not in row["command"]
            and f"--user-data-dir={prefix}" in row["command"].replace('"', "")]


def sweep_browsers_under(folder: Path) -> list[int]:
    """folder 아래 프로필로 뜬 브라우저를 전부 끈다 > 끈 pid (세션 끝 안전망)"""
    pids = browser_pids_under(folder)
    for pid in pids:
        kill_browser(pid, grace=1.0)
    return pids
