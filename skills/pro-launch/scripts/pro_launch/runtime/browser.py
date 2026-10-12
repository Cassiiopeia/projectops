"""브라우저 상태 파일 · Playwright 준비 상태 · 어떤 브라우저로 띄울지. web 과 doctor 가 함께 쓴다."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from common.state import launch_file, venv_dir, venv_python, venv_site_packages

import browser_pick

from pro_launch.runtime.context import state_home
from pro_launch.runtime.procs import pid_alive


# 마지막으로 쓴 뒤 이만큼 지나면 "방치됐다"고 본다 — 다른 세션이 쓰는 중인지 가를 근거 (#825)
_STALE_BROWSER_HOURS = 6


def open_browser_status(state_f: Path) -> dict | None:
    """이 레포에 떠 있는 브라우저가 있나, 언제 마지막으로 썼나. 없으면 None."""
    st = read_state(state_f) if state_f.is_file() else {}
    pid = st.get("pid")
    if not pid:
        return None
    alive = pid_alive(int(pid))
    used = st.get("last_used") or st.get("opened_at")
    idle_h = None
    try:
        idle_h = round((time.time() - time.mktime(time.strptime(used, "%Y-%m-%d %H:%M:%S"))) / 3600, 1)
    except (TypeError, ValueError):
        pass
    stale = alive and idle_h is not None and idle_h >= _STALE_BROWSER_HOURS
    return {"pid": pid, "alive": alive, "opened_at": st.get("opened_at"), "last_used": used,
            "idle_hours": idle_h, "readonly": bool(st.get("readonly")), "stale": stale,
            "hint": (f"{idle_h}시간째 안 쓴 브라우저다 — 다른 세션이 쓰는 중이 아니면 web close 로 정리하거나 web open 으로 다시 붙는다"
                     if stale else None)}


#
# agent가 스크린샷을 보고 다음 수를 정하므로 조작이 여러 번의 CLI 호출로 쪼개진다.
# 상주 데몬을 만들지 않고 **CDP 재연결**로 푼다:
#   open  → --remote-debugging-port 로 띄우고 포트를 상태파일에 적는다
#   이후  → connect_over_cdp 로 그 브라우저에 붙었다 떨어진다 (세션·쿠키 유지)
#
# ⚠️ 붙어 있는 동안에만 사는 것이 있다 — 콘솔 훅·뷰포트·응답 바꿔치기. 연결이 끊기면
# 같이 사라진다(#625 실측). 그래서 상태 파일에 적어 두고 **붙을 때마다 다시 건다.**
_WEB_STATE = "browser.json"


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
            "error": "웹을 띄우려면 Playwright가 필요합니다",
            "fix": "web setup  # 전용 환경을 만들고 브라우저까지 받습니다 (약 100MB)",
            "manual": f"{sys.executable} -m venv {vd} && "
                      f"{vd}/bin/pip install playwright pillow && "
                      f"{vd}/bin/python -m playwright install chromium",
            "why": ("별도 설치물에 기대지 않으려고 Playwright를 직접 씁니다. "
                    "시스템 파이썬을 건드리지 않도록 전용 환경에 깝니다"),
            "ask_user": "웹을 띄우려면 브라우저(약 100MB)를 받아야 합니다. 설치할까요?",
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
    return {"ready": True, "venv": str(venv_dir()) if venv_python() else "시스템"}


def browser_choice() -> dict:
    """이번에 쓸 브라우저. 어느 것을 왜 골랐는지까지 — 조용히 바꾸지 않는다 (#857)."""
    return browser_pick.resolve(bundled_chromium_path())
