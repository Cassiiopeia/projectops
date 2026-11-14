"""Check image tools (Pillow · numpy) are installed"""
from __future__ import annotations

from common.emit import emit


def _require_imaging():
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return emit({
            "ok": False, "code": "imaging_missing",
            "error": "Pillow and numpy are required",
            "hint": "python3 -m pip install pillow numpy",
        })
    return None
