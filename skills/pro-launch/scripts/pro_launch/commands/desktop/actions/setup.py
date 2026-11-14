"""`desktop setup` — install per-OS packages into the shared venv (Windows: mss, comtypes; macOS: mss, pyobjc)."""
from __future__ import annotations

import desktop_input

from common.state import venv_dir

from pro_launch.registry import Action
from pro_launch.runtime.output import out
from pro_launch.runtime.venv_install import ensure_venv, pip_install

# Per-OS packages — kept here so they are known without importing the backend module (importing needs those packages)
PACKAGES = {"windows": ("mss", "comtypes"),
            "macos": ("mss", "pyobjc-framework-ApplicationServices", "pyobjc-framework-Quartz")}


def _desktop_setup(force: bool) -> dict:
    key = desktop_input.platform_key()
    if key not in PACKAGES:
        return {"ok": False, "code": "unsupported_on_platform",
                "error": f"desktop control supports {', '.join(PACKAGES)} for now"}
    steps: list = []
    vpy, failure = ensure_venv(steps, force=force)
    if failure:
        return failure
    if not pip_install(vpy, list(PACKAGES[key]), steps):
        return {"ok": False, "code": "pip_failed", "steps": steps, "platform": key,
                "error": f"Could not install {' '.join(PACKAGES[key])}",
                "next": f"On an internal network, point pip at your PyPI mirror and run: pip install {' '.join(PACKAGES[key])}"}
    return {"ok": True, "steps": steps, "platform": key, "venv": str(venv_dir()),
            "summary": f"Ready for desktop control ({key})", "next": "desktop doctor"}


def configure(p) -> None:
    p.add_argument("--force", action="store_true", help="rebuild the venv even if it exists")


def execute(args) -> int:
    return out(_desktop_setup(args.force))


ACTION = Action(name="setup", needs="nothing", run=execute, configure=configure, options=(), device_use="none",
                help="Install the desktop-control packages into the shared venv (a few MB)", example="desktop setup")
