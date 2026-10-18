"""최근에 쓴 프로젝트 루트 기록 · 후보 찾기 (#885).

agent 셸은 호출마다 작업 폴더가 바뀐다. 레포 밖에서 불리면 루트를 못 찾아 git_not_found·browser_not_open 이 났다.
이 스킬로 쓴 루트를 이 컴퓨터 공용 자리에 적어 두고, 작업 폴더가 레포가 아니면 가장 최근 것을 쓴다.

  ~/.projectops/launch/_machine/recent_roots.json   {"roots": [{"path", "at"}]}  최근 것이 앞
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from common.state import MACHINE_BUCKET, base_dir, is_scratch_root, launch_file

from pro_launch.runtime.procs import pid_alive

RECENT_ROOTS_FILE = "recent_roots.json"
MAX_RECENT_ROOTS = 10
# 같은 루트를 이 간격 안에 다시 쓰면 파일을 다시 쓰지 않는다 (명령마다 쓰기 방지)
REWRITE_INTERVAL_SECONDS = 600
BROWSER_STATE_FILE = "browser.json"


def recent_roots_path() -> Path:
    return base_dir() / "launch" / MACHINE_BUCKET / RECENT_ROOTS_FILE


def is_git_work_tree(path: Path) -> bool:
    """path 가 git 작업 트리 안인가."""
    try:
        result = subprocess.run(["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def load_recent_roots() -> list[dict]:
    """[{path, at}] 최근 순. 지금 없는 폴더는 뺀다. 못 읽으면 빈 목록."""
    try:
        data = json.loads(recent_roots_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("roots") if isinstance(data, dict) else None
    # 예전에 적힌 임시 폴더(jobs/tmp/formedit 등)는 후보에서 뺀다 (#932)
    return [r for r in rows or [] if isinstance(r, dict) and r.get("path") and Path(r["path"]).is_dir()
            and not is_scratch_root(Path(r["path"]))]


def remember_root(root: Path) -> None:
    """이번에 쓴 루트를 맨 앞에 둔다. 기록 실패는 명령을 막지 않는다."""
    path_text = str(root)
    rows = load_recent_roots()
    now = time.time()
    if rows and rows[0]["path"] == path_text and now - float(rows[0].get("at") or 0) < REWRITE_INTERVAL_SECONDS:
        return
    rows = [{"path": path_text, "at": now}] + [r for r in rows if r["path"] != path_text]
    target = recent_roots_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps({"roots": rows[:MAX_RECENT_ROOTS]}), encoding="utf-8")
        os.replace(temporary, target)
    except OSError:
        pass


def last_used_root() -> Path | None:
    rows = load_recent_roots()
    return Path(rows[0]["path"]) if rows else None


def has_live_browser(root: Path) -> bool:
    """그 레포에 이 스킬이 띄운 브라우저가 살아 있나 (상태 파일의 pid 로 본다)."""
    try:
        state = json.loads(launch_file(root, BROWSER_STATE_FILE).read_text(encoding="utf-8"))
        return bool(state.get("cdp")) and bool(state.get("pid")) and pid_alive(int(state["pid"]))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def root_candidates() -> list[dict]:
    """다시 부를 때 --root 로 넘길 후보: 최근 루트 + 브라우저가 살아 있는지. 살아 있는 것이 앞."""
    rows = [{"path": r["path"], "has_live_browser": has_live_browser(Path(r["path"]))}
            for r in load_recent_roots()]
    return sorted(rows, key=lambda row: not row["has_live_browser"])
