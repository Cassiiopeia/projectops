"""연습 화면 배치 기억: 글자 크기 · 패널 너비 · 슬라이드 높이 > 덱 안 .presentation/layout.json
서버 포트가 실행마다 달라 브라우저 저장소로는 남지 않음 > 덱 상태 폴더에 저장 (덱 버전 계산에서 빠짐)
"""
from __future__ import annotations

import json
from pathlib import Path

from pro_presentation.settings import LAYOUT_FILE_NAME, STATE_DIR_NAME

# 배치 값 허용 범위 (최소, 최대). 표에 없는 키와 범위 밖 값은 버림
LAYOUT_RANGES = {
    "script_scale": (0.5, 2.5),          # 대본 글자 배율 (1 = 기본 크기)
    "panel_scale": (0.5, 2.5),           # 오른쪽 카드 글자 배율
    "panel_width_pixels": (200, 2400),   # 오른쪽 열 너비 (px)
    "slide_height_ratio": (0.1, 0.9),    # 슬라이드 높이 (창 높이 대비)
}


def layout_file(deck_dir: Path) -> Path:
    return deck_dir / STATE_DIR_NAME / LAYOUT_FILE_NAME


def clean_layout(raw) -> dict:
    """아는 키 + 범위 안 숫자만 남김 (bool 제외)"""
    if not isinstance(raw, dict):
        return {}
    cleaned = {}
    for name, (minimum, maximum) in LAYOUT_RANGES.items():
        value = raw.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and minimum <= value <= maximum:
            cleaned[name] = value
    return cleaned


def read_layout(deck_dir: Path) -> dict:
    """저장된 배치 (없거나 깨졌으면 빈 dict = 기본 배치)"""
    try:
        return clean_layout(json.loads(layout_file(deck_dir).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def save_layout(deck_dir: Path, raw) -> dict:
    """브라우저가 보낸 배치 전체 > 검증 > 저장. 저장된 값 반환"""
    cleaned = clean_layout(raw)
    target = layout_file(deck_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cleaned), encoding="utf-8")
    return cleaned
