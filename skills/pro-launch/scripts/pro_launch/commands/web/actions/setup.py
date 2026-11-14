"""`web setup` — prepare the dedicated environment, Playwright and browser."""
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
    """Dedicated venv + Playwright + Pillow + Chromium. About 100MB, so the caller asks first."""
    vd = venv_dir()
    steps = []
    vpy, failure = ensure_venv(steps, force=force)
    if failure:
        return failure
    # Install Pillow too — a way to shrink captures without touching the system
    pip_ok = pip_install(vpy, ["playwright", "pillow"], steps)
    if not pip_ok:
        # Internal networks: if the index is blocked but system Python already has Playwright, go with it (#857)
        if importlib.util.find_spec("playwright") is None:
            return {"ok": False, "code": "pip_failed", "steps": steps,
                    "error": "Could not install playwright",
                    "next": ("On an internal network, point pip at your PyPI mirror and install `pip install playwright pillow` "
                             "system-wide first. The installed Chrome/Edge is used as the browser")}
        steps.append({"step": "use system Playwright", "ok": True, "error": None,
                      "note": "Package index unreachable — skipped the dedicated env and used the system install"})
    # If a usable browser already exists, skip the 100MB download. With a bundle, behavior is unchanged
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
                           capture_output=True, text=True, errors="replace", timeout=1800)
        steps.append({"step": "download chromium", "ok": r.returncode == 0,
                      "error": (r.stderr or "")[-300:] or None})
        if r.returncode == 0:
            return {"ok": True, "steps": steps, "venv": str(vd), "browser": "Playwright Chromium",
                    "summary": "Ready to launch the web", "next": "web open --url <url>"}
    else:
        steps.append({"step": "download chromium", "ok": False, "skipped": True,
                      "error": f"Not downloaded — {host} is unreachable"})
    # Download failed — fall back to an installed Chrome or Edge
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
