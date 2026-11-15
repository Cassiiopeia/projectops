"""Step that creates the dedicated venv and installs packages — shared by `web setup` and `desktop setup` (#985).

Results come back as a step list (`steps`). The caller appends its own steps and reports them all at once.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from common.state import venv_dir, venv_python


def ensure_venv(steps: list, force: bool = False) -> tuple[Path | None, dict | None]:
    """Create the venv if missing (or force). (venv python, failure result) — the first is None on failure."""
    if not venv_python() or force:
        r = subprocess.run([sys.executable, "-m", "venv", str(venv_dir())],
                           capture_output=True, text=True, errors="replace")
        steps.append({"step": "create virtualenv", "ok": r.returncode == 0,
                      "error": (r.stderr or "")[-300:] or None})
        if r.returncode != 0:
            return None, {"ok": False, "code": "venv_failed", "steps": steps,
                          "error": "Could not create the virtualenv",
                          "next": "Read steps for the cause. On Debian or Ubuntu install python3-venv; elsewhere check disk space and folder permissions"}
    vpy = venv_python()
    if vpy is None:
        return None, {"ok": False, "code": "venv_missing", "steps": steps,
                      "error": "Could not find the virtualenv Python"}
    return vpy, None


def pip_install(vpy: Path, packages: list[str], steps: list, timeout: int = 900) -> bool:
    """Install packages into the venv. Records the result in steps and returns success."""
    try:
        r = subprocess.run([str(vpy), "-m", "pip", "install", "-q", *packages],
                           capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        r = None
    ok = r is not None and r.returncode == 0
    steps.append({"step": f"install {' · '.join(packages)}", "ok": ok,
                  "error": None if ok else ((r.stderr or "")[-300:] if r else "timed out") or None})
    return ok
