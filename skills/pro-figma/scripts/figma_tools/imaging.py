"""이미지 도구(Pillow · numpy) 설치 확인"""
from __future__ import annotations

from common.emit import emit


def _require_imaging():
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return emit({
            "ok": False, "code": "imaging_missing",
            "error": "Pillow 와 numpy 가 필요합니다",
            "hint": "python3 -m pip install pillow numpy",
        })
    return None
