"""Remember practice screen layout: font size · panel width · slide height > the deck's .presentation/layout.json
The server port changes per run, so browser storage does not persist > saved in the deck state folder (excluded from deck version)
"""
from __future__ import annotations

import json
from pathlib import Path

from pro_presentation.settings import LAYOUT_FILE_NAME, STATE_DIR_NAME

# Allowed layout value ranges (min, max). Keys not in the table and out-of-range values are dropped
LAYOUT_RANGES = {
    "script_scale": (0.5, 2.5),          # script font scale (1 = default size)
    "panel_scale": (0.5, 2.5),           # right card font scale
    "panel_width_pixels": (200, 2400),   # right column width (px)
    "slide_height_ratio": (0.1, 0.9),    # slide height (relative to window height)
}


def layout_file(deck_dir: Path) -> Path:
    return deck_dir / STATE_DIR_NAME / LAYOUT_FILE_NAME


def clean_layout(raw) -> dict:
    """Keep only known keys + numbers in range (bool excluded)"""
    if not isinstance(raw, dict):
        return {}
    cleaned = {}
    for name, (minimum, maximum) in LAYOUT_RANGES.items():
        value = raw.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and minimum <= value <= maximum:
            cleaned[name] = value
    return cleaned


def read_layout(deck_dir: Path) -> dict:
    """Saved layout (empty dict = default layout if missing or broken)"""
    try:
        return clean_layout(json.loads(layout_file(deck_dir).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def save_layout(deck_dir: Path, raw) -> dict:
    """Whole layout sent by the browser > validate > save. Returns the saved values"""
    cleaned = clean_layout(raw)
    target = layout_file(deck_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cleaned), encoding="utf-8")
    return cleaned
