"""`web setup` — 전용 환경 · Playwright · 브라우저를 준비한다."""
from __future__ import annotations

import importlib.util
import subprocess

from common.state import venv_dir

import browser_pick

from pro_launch.registry import Action
from pro_launch.runtime.browser import bundled_chromium_path
from pro_launch.runtime.output import out
from pro_launch.runtime.venv_install import ensure_venv, pip_install


def _web_setup(force: bool = False) -> dict:
    """전용 가상환경 + Playwright + Pillow + Chromium. 약 100MB 라 부르는 쪽이 먼저 묻는다."""
    vd = venv_dir()
    steps = []
    vpy, failure = ensure_venv(steps, force=force)
    if failure:
        return failure
    # Pillow 를 함께 깐다 — 캡처를 줄이는 수단을 시스템을 건드리지 않고 확보한다
    pip_ok = pip_install(vpy, ["playwright", "pillow"], steps)
    if not pip_ok:
        # 내부망: 인덱스가 막혀도 시스템 파이썬에 Playwright 가 이미 있으면 그대로 간다 (#857)
        if importlib.util.find_spec("playwright") is None:
            return {"ok": False, "code": "pip_failed", "steps": steps,
                    "error": "Could not install playwright",
                    "next": ("On an internal network, point pip at your PyPI mirror and install `pip install playwright pillow` "
                             "system-wide first. The installed Chrome/Edge is used as the browser")}
        steps.append({"step": "use system Playwright", "ok": True, "error": None,
                      "note": "Package index unreachable — skipped the dedicated env and used the system install"})
    # 이미 쓸 브라우저가 있으면 100MB 를 받지 않는다. 번들이 있으면 기존 동작 그대로다
    pick = browser_pick.resolve(bundled_chromium_path())
    if pick.get("error"):
        return {"ok": False, "code": "browser_env_invalid", "steps": steps, "error": pick["error"],
                "next": f"Fix or unset {browser_pick.ENV_VAR}"}
    if pick["source"] in ("env", "bundled"):
        steps.append({"step": "download chromium", "ok": True, "error": None,
                      "skipped": True, "note": pick["reason"]})
        return {"ok": True, "steps": steps, "venv": str(vd), "browser": pick["label"],
                "summary": f"Ready to launch the web ({pick['label']})", "next": "web open --url <url>"}
    host = browser_pick.download_host()
    reachable = browser_pick.download_host_reachable(host)
    if reachable:
        r = subprocess.run([str(vpy), "-m", "playwright", "install", "chromium"],
                           capture_output=True, text=True, timeout=1800)
        steps.append({"step": "download chromium", "ok": r.returncode == 0,
                      "error": (r.stderr or "")[-300:] or None})
        if r.returncode == 0:
            return {"ok": True, "steps": steps, "venv": str(vd), "browser": "Playwright Chromium",
                    "summary": "Ready to launch the web", "next": "web open --url <url>"}
    else:
        steps.append({"step": "download chromium", "ok": False, "skipped": True,
                      "error": f"Not downloaded — {host} is unreachable"})
    # 못 받았다 — 설치된 Chrome·Edge 가 있으면 그것으로 간다
    if pick["exe"]:
        return {"ok": True, "steps": steps, "venv": str(vd), "browser": pick["label"],
                "browser_source": "system",
                "summary": f"Could not download the bundled browser; using the installed browser ({pick['label']})",
                "next": "web open --url <url>"}
    return {"ok": False, "code": "browser_failed", "steps": steps,
            "error": "Could not download a browser and found no installed Chrome/Edge",
            "next": f"Install Chrome or Edge, or set {browser_pick.ENV_VAR}=<path to the executable>"}


def configure(p) -> None:
    p.add_argument("--force", action="store_true", help="setup: rebuild even if it already exists")


def execute(args) -> int:
    return out(_web_setup(force=args.force))


ACTION = Action(name="setup", needs="nothing", run=execute, configure=configure, options=(),
                help="Prepare the dedicated env, Playwright and browser (about 100MB)", example="web setup")
