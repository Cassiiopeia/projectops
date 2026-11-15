"""Supported apps: one adapter module per app (NAME, CONNECTION, inspect(); relay apps add fresh_link())
Add an app: write harness/<name>.md + remote_apps/<name>.py, then register it in SUPPORTED_APPS
"""
from __future__ import annotations

from pathlib import Path

from tunnel import state

from . import orca, paseo

# name > adapter module. CONNECTION: "tunnel" (cloudflared quick tunnel + saved link) or "relay" (app makes the link)
SUPPORTED_APPS = {adapter.NAME: adapter for adapter in (orca, paseo)}
# Bundled harness folder (skill folder/harness)
BUNDLED_HARNESS_DIR = Path(__file__).resolve().parents[2] / "harness"


def harness_path(app: str) -> Path | None:
    """Harness doc for the app: local override first, then the bundled copy. None if neither exists"""
    for folder in (state.HARNESS_OVERRIDE_DIR, BUNDLED_HARNESS_DIR):
        candidate = folder / f"{app}.md"
        if candidate.is_file():
            return candidate
    return None
