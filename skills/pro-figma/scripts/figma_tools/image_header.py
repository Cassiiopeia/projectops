"""이미지 헤더 판독: PNG IHDR·JPEG SOF > 형식·크기·알파 (표준 라이브러리만)

Pillow 가 없는 내부망에서도 store-check 가 돌아야 해서 imaging.py(Pillow) 를 쓰지 않는다.
픽셀은 읽지 않는다 — 헤더와 PNG 보조 청크(tRNS)까지만.
"""
from __future__ import annotations

import struct
from pathlib import Path

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# PNG color type: 0 회색, 2 RGB, 3 팔레트, 4 회색+알파, 6 RGBA
_PNG_ALPHA_COLOR_TYPES = (4, 6)
# JPEG SOF 마커 (C4 허프만·C8 예약·CC 산술 조건은 SOF 아님)
_JPEG_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                     0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
# 길이 필드 없는 단독 마커 (RST0~7, SOI, TEM)
_JPEG_STANDALONE_MARKERS = set(range(0xD0, 0xD8)) | {0x01, 0xD8}


def read_image_header(path: Path) -> dict:
    """파일 > {format, width, height, has_alpha, bit_depth?, color_type?} 또는 {error}"""
    try:
        data = path.read_bytes()
    except OSError as e:
        return {"error": f"cannot read file: {e}"}
    if data.startswith(_PNG_SIGNATURE):
        return _read_png(data)
    if data[:2] == b"\xff\xd8":
        return _read_jpeg(data)
    return {"error": "not a PNG or JPEG file"}


def _read_png(data: bytes) -> dict:
    """IHDR(크기·비트 깊이·color type) + IDAT 전 tRNS 유무 > 알파 판정"""
    if len(data) < 33 or data[12:16] != b"IHDR":
        return {"error": "PNG without a valid IHDR chunk"}
    width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    has_transparency_chunk = False
    # 청크 순회: 길이(4) 타입(4) 데이터 CRC(4)
    offset = 8
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        if chunk_type == b"tRNS":
            has_transparency_chunk = True
            break
        if chunk_type in (b"IDAT", b"IEND"):
            break
        offset += 12 + length
    return {"format": "png", "width": width, "height": height,
            "bit_depth": bit_depth, "color_type": color_type,
            "has_alpha": color_type in _PNG_ALPHA_COLOR_TYPES or has_transparency_chunk}


def _read_jpeg(data: bytes) -> dict:
    """마커 순회 > 첫 SOF 의 높이·너비 (JPEG 은 알파 없음)"""
    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            return {"error": "JPEG marker stream is broken"}
        marker = data[offset + 1]
        if marker == 0xFF:                       # 채움 바이트
            offset += 1
            continue
        if marker in _JPEG_STANDALONE_MARKERS:
            offset += 2
            continue
        if marker == 0xD9:                       # EOI
            break
        segment_length = struct.unpack(">H", data[offset + 2:offset + 4])[0]
        if marker in _JPEG_SOF_MARKERS:
            if offset + 9 > len(data):
                break
            height, width = struct.unpack(">HH", data[offset + 5:offset + 9])
            return {"format": "jpeg", "width": width, "height": height, "has_alpha": False}
        offset += 2 + segment_length
    return {"error": "JPEG without a frame header (SOF)"}
