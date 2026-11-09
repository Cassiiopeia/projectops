"""이미지 사실 수집 (표준 라이브러리만): PNG·JPEG·WebP > 형식·크기·알파 채널 + 요청 규격 대조"""
from __future__ import annotations

import struct
from pathlib import Path

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
# PNG 색 형식 중 알파 채널 포함: 4 회색+알파, 6 RGBA
PNG_ALPHA_COLOR_TYPES = (4, 6)
# JPEG 크기가 담긴 SOF 마커 (SOF0~SOF15, DHT·JPG·DAC 제외)
JPEG_SIZE_MARKERS = set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


def _png(data: bytes) -> dict:
    width, height = struct.unpack(">II", data[16:24])
    color_type = data[25]
    has_alpha = color_type in PNG_ALPHA_COLOR_TYPES or b"tRNS" in data[:4096]
    return {"format": "png", "width": width, "height": height, "has_alpha": has_alpha}


def _jpeg(data: bytes) -> dict:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        segment_length = struct.unpack(">H", data[index + 2:index + 4])[0]
        if marker in JPEG_SIZE_MARKERS:
            height, width = struct.unpack(">HH", data[index + 5:index + 9])
            return {"format": "jpeg", "width": width, "height": height, "has_alpha": False}
        index += 2 + segment_length
    return {"format": "jpeg", "width": None, "height": None, "has_alpha": False}


def _webp(data: bytes) -> dict:
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return {"format": "webp", "width": width, "height": height, "has_alpha": bool(data[20] & 0x10)}
    if chunk == b"VP8L":
        bits = int.from_bytes(data[21:25], "little")
        return {"format": "webp", "width": (bits & 0x3FFF) + 1, "height": ((bits >> 14) & 0x3FFF) + 1,
                "has_alpha": bool((bits >> 28) & 1)}
    if chunk == b"VP8 ":
        width, height = struct.unpack("<HH", data[26:30])
        return {"format": "webp", "width": width & 0x3FFF, "height": height & 0x3FFF, "has_alpha": False}
    return {"format": "webp", "width": None, "height": None, "has_alpha": None}


def read_facts(path: Path) -> dict:
    try:
        data = path.read_bytes()
    except OSError as error:
        return {"path": str(path), "readable": False, "error": str(error)}
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        facts = _png(data)
    elif data[:2] == b"\xff\xd8":
        facts = _jpeg(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        facts = _webp(data)
    else:
        facts = {"format": "unknown", "width": None, "height": None, "has_alpha": None}
    return {"path": str(path), "readable": True, "bytes": len(data), **facts}


def parse_size(text: str | None) -> tuple[int, int] | None:
    """'1536x1024' > (1536, 1024)"""
    if not text:
        return None
    width, _, height = text.lower().partition("x")
    return (int(width), int(height)) if width.isdigit() and height.isdigit() else None


def find_problems(facts: dict, expected_size: tuple[int, int] | None, is_alpha_required: bool) -> list[str]:
    """요청 규격 대조 > 어긋난 항목 목록 (빈 목록이면 통과)"""
    if not facts.get("readable"):
        return ["unreadable file"]
    problems = []
    if facts.get("format") == "unknown":
        problems.append("not a PNG, JPEG or WebP image")
    if expected_size and (facts.get("width"), facts.get("height")) != expected_size:
        problems.append(f"size {facts.get('width')}x{facts.get('height')} != requested {expected_size[0]}x{expected_size[1]}")
    if is_alpha_required and not facts.get("has_alpha"):
        problems.append("no alpha channel (transparent background was requested)")
    return problems


def list_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
