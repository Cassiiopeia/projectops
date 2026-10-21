"""브라우저 상태 파일 · Playwright 준비 상태 · 어떤 브라우저로 띄울지. web 과 doctor 가 함께 쓴다."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from common.state import base_dir, launch_file, venv_dir, venv_python, venv_site_packages

import browser_pick

from pro_launch.runtime.context import state_home
from pro_launch.runtime.procs import pid_alive, process_table


# 마지막으로 쓴 뒤 이만큼 지나면 "방치됐다"고 본다 — 다른 세션이 쓰는 중인지 가를 근거 (#825)
_STALE_BROWSER_HOURS = 6


def idle_hours(state: dict) -> float | None:
    """마지막 사용(없으면 연 시각) 뒤 지난 시간. 기록이 없거나 못 읽으면 None."""
    used = state.get("last_used") or state.get("opened_at")
    try:
        return round((time.time() - time.mktime(time.strptime(used, "%Y-%m-%d %H:%M:%S"))) / 3600, 1)
    except (TypeError, ValueError):
        return None


def open_browser_status(state_f: Path) -> dict | None:
    """이 레포에 떠 있는 브라우저가 있나, 언제 마지막으로 썼나. 없으면 None."""
    st = read_state(state_f) if state_f.is_file() else {}
    pid = st.get("pid")
    if not pid:
        return None
    alive = pid_alive(int(pid))
    used = st.get("last_used") or st.get("opened_at")
    idle_h = idle_hours(st)
    stale = alive and idle_h is not None and idle_h >= _STALE_BROWSER_HOURS
    return {"pid": pid, "alive": alive, "opened_at": st.get("opened_at"), "last_used": used,
            "idle_hours": idle_h, "readonly": bool(st.get("readonly")), "stale": stale,
            "hint": (f"Browser idle for {idle_h} hours — unless another session is using it, clean up with web close or reattach with web open"
                     if stale else None)}


#
# agent가 스크린샷을 보고 다음 수를 정하므로 조작이 여러 번의 CLI 호출로 쪼개진다.
# 상주 데몬을 만들지 않고 **CDP 재연결**로 푼다:
#   open  → --remote-debugging-port 로 띄우고 포트를 상태파일에 적는다
#   이후  → connect_over_cdp 로 그 브라우저에 붙었다 떨어진다 (세션·쿠키 유지)
#
# ⚠️ 붙어 있는 동안에만 사는 것이 있다 — 콘솔 훅·뷰포트·응답 바꿔치기. 연결이 끊기면
# 같이 사라진다(#625 실측). 그래서 상태 파일에 적어 두고 **붙을 때마다 다시 건다.**
# 브라우저 상태 파일 이름 — 레포 버킷 · 공용 프로필 폴더 공통 (#956)
WEB_STATE_FILE_NAME = "browser.json"
_WEB_STATE = WEB_STATE_FILE_NAME


def state_path(root: Path) -> Path:
    state_home(root)
    return launch_file(root, _WEB_STATE)


def read_state(f: Path) -> dict:
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(f: Path, state: dict) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def require_playwright() -> tuple[object | None, dict | None]:
    """Playwright를 불러온다. 전용 가상환경 → 시스템 순으로 본다.

    함수 안에서 import하는 이유: 웹을 안 쓰는 프로젝트에서 이 스크립트가 통째로
    죽으면 안 된다. 앱·서버는 Playwright 없이 돌아가야 한다.
    """
    sp = venv_site_packages()
    if sp and str(sp) not in sys.path:
        sys.path.insert(0, str(sp))
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright, None
    except ImportError:
        vd = venv_dir()
        return None, {
            "ok": False, "code": "playwright_missing",
            "error": "Playwright is required to open the web",
            "fix": "web setup  # creates a dedicated environment and downloads the browser (about 100MB)",
            "manual": f"{sys.executable} -m venv {vd} && "
                      f"{vd}/bin/pip install playwright pillow && "
                      f"{vd}/bin/python -m playwright install chromium",
            "why": ("Playwright is used directly to avoid depending on separate installs. "
                    "It goes into a dedicated environment so the system Python is untouched"),
            "ask_user": "Opening the web needs a browser download (about 100MB). Install it?",
        }


def bundled_chromium_path() -> str | None:
    """Playwright 번들 Chromium 이 있어야 할 자리. Playwright 가 없거나 못 읽으면 None."""
    sync_playwright, err = require_playwright()
    if err:
        return None
    try:
        with sync_playwright() as pw:
            return pw.chromium.executable_path
    except Exception:
        return None


def playwright_state() -> dict:
    ok, err = require_playwright()
    if err:
        return {"ready": False, "reason": err["error"], "fix": err["fix"],
                "ask_user": err["ask_user"]}
    return {"ready": True, "venv": str(venv_dir()) if venv_python() else "system"}


def browser_choice() -> dict:
    """이번에 쓸 브라우저. 어느 것을 왜 골랐는지까지 — 조용히 바꾸지 않는다 (#857)."""
    return browser_pick.resolve(bundled_chromium_path())


# ── 버려진 브라우저 찾기 (#921) ──────────────────────────────────────────
#
# web open 은 브라우저를 부모 없는 독립 프로세스로 띄운다. 상태 파일이 지워지거나(테스트 임시 폴더)
# 다른 프로필로 다시 띄우면 아무도 그 브라우저를 끄지 않는다 — headless Chrome 이 쌓여 사용자의
# Chrome(파일 열기)을 가로챘다(실측). 우리 프로필로 뜬 것만 본다. 사용자 Chrome 은 프로필이 달라 안 걸린다.

# web open 이 쓰는 프로필 폴더 이름 (state_home/.browser-profile)
PROFILE_FOLDER_NAME = ".browser-profile"
# 명령줄의 프로필 경로 — 우리 프로필은 항상 .browser-profile 로 끝난다 (공백 경로 포함)
_USER_DATA_DIR_PATTERN = re.compile(r'--user-data-dir=("?)(.+?[\\/]\.browser-profile)\1(?=\s|$)')
# 상태 루트가 임시 폴더여도(PROJECTOPS_HOME 을 돌린 테스트) 이 모양이면 우리 것
_LAUNCH_PATH_MARKERS = ("/.projectops/launch/", "/.projectops/agent-test/")
# 상태 파일이 가리키는데도 정리하는 방치 시간(시간)
STALE_REAP_IDLE_HOURS = 12
# 막 띄워 아직 상태 파일을 안 쓴 브라우저를 건드리지 않는 시간(초) — open 의 포트 대기는 최대 약 15초
STARTING_GRACE_SECONDS = 120


def _normalized_path(path: str) -> str:
    return os.path.realpath(path).replace("\\", "/")


def is_owned_profile(profile: str) -> bool:
    """pro-launch 가 띄운 프로필인가: 지금 상태 루트 아래 · 또는 .projectops/launch 모양의 경로."""
    normalized = _normalized_path(profile)
    if any(marker in normalized for marker in _LAUNCH_PATH_MARKERS):
        return True
    return normalized.startswith(_normalized_path(str(base_dir() / "launch")) + "/")


def owned_browser_processes(table: list[dict]) -> list[dict]:
    """프로세스 목록 > 우리 프로필로 뜬 브라우저 본 프로세스들 (렌더러 · GPU 같은 --type= 자식 제외)."""
    found = []
    for row in table:
        command = row.get("command") or ""
        if "--remote-debugging-port=" not in command or "--type=" in command:
            continue
        match = _USER_DATA_DIR_PATTERN.search(command)
        if match and is_owned_profile(match.group(2)):
            found.append({**row, "profile": match.group(2)})
    return found


def _stale_reasons(process: dict, maximum_idle_hours: float) -> tuple[list[str], dict]:
    """(정리할 사유들, 상태 정보). 사유 3개: profile_gone · state_not_pointing · idle"""
    profile = Path(process["profile"])
    state = read_state(profile.parent / _WEB_STATE) if profile.parent.is_dir() else {}
    elapsed = process.get("elapsed_seconds")
    is_starting = elapsed is None or elapsed < STARTING_GRACE_SECONDS
    idle = idle_hours(state) if state else None
    info = {"state_file": str(profile.parent / _WEB_STATE) if state else None, "idle_hours": idle}
    if not profile.is_dir():
        return ["profile_gone"], info
    if str(state.get("pid")) != str(process["pid"]):
        # 막 띄운 것은 상태 파일을 아직 안 썼을 수 있다
        return ([] if is_starting else ["state_not_pointing"]), info
    # 부모 없음: POSIX 는 PPID 1 로 넘어가고, 윈도우는 죽은 부모 번호가 남는다
    parent_pid = process.get("ppid")
    is_orphan = not parent_pid or parent_pid == 1 or not pid_alive(int(parent_pid))
    if is_orphan and idle is not None and idle >= maximum_idle_hours:
        return ["idle"], info
    return [], info


def find_stale_browsers(maximum_idle_hours: float = STALE_REAP_IDLE_HOURS) -> dict:
    """pro-launch 브라우저를 버려진 것(stale) · 쓰는 중(kept)으로 가른다. doctor 와 web close --stale 이 쓴다.

    > {"readable", "stale": [{pid, profile, reasons, ...}], "kept": [...]}. 프로세스 목록을 못 읽으면 readable False
    """
    table = process_table()
    if table is None:
        return {"readable": False, "stale": [], "kept": []}
    stale, kept = [], []
    for process in owned_browser_processes(table):
        reasons, info = _stale_reasons(process, maximum_idle_hours)
        entry = {"pid": process["pid"], "ppid": process.get("ppid"), "profile": process["profile"],
                 "elapsed_seconds": process.get("elapsed_seconds"), **info}
        (stale if reasons else kept).append({**entry, "reasons": reasons} if reasons else entry)
    return {"readable": True, "stale": stale, "kept": kept}
