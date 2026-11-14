"""Pick the capture browser: same rules as pro-launch (env var > bundled Chromium > installed Chrome, Edge)
Standard library only (the capture worker imports it directly from the dedicated venv Python)
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

# skills/pro-launch/scripts/browser_pick.py (this file: skills/pro-ui-design/scripts/pro_ui_design/)
BROWSER_PICK_FILE = Path(__file__).resolve().parents[3] / "pro-launch" / "scripts" / "browser_pick.py"


def _load_browser_pick():
    spec = importlib.util.spec_from_file_location("browser_pick", BROWSER_PICK_FILE)
    if spec is None or not BROWSER_PICK_FILE.is_file():
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_browser_executable(playwright) -> str | None:
    """Executable path. None leaves it to the Playwright default"""
    browser_pick = _load_browser_pick()
    if browser_pick is None:
        return None
    try:
        bundled = playwright.chromium.executable_path
    except Exception:  # Playwright internal error: treat as no bundle
        bundled = None
    return browser_pick.resolve(bundled).get("exe")
