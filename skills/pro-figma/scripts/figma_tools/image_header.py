"""Image header reading: PNG IHDR·JPEG SOF > format·size·alpha (standard library only)

store-check must run on internal networks without Pillow, so imaging.py (Pillow) is not used.
Pixels are not read — only the header and the PNG ancillary chunk (tRNS).
"""
from __future__ import annotations

import struct
from pathlib import Path

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# PNG color type: 0 gray, 2 RGB, 3 palette, 4 gray+alpha, 6 RGBA
_PNG_ALPHA_COLOR_TYPES = (4, 6)
# JPEG SOF markers (C4 Huffman·C8 reserved·CC arithmetic conditioning are not SOF)
_JPEG_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                     0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
# Standalone markers without a length field (RST0~7, SOI, TEM)
_JPEG_STANDALONE_MARKERS = set(range(0xD0, 0xD8)) | {0x01, 0xD8}


def read_image_header(path: Path) -> dict:
    """File > {format, width, height, has_alpha, bit_depth?, color_type?} or {error}"""
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
    """IHDR (size·bit depth·color type) + tRNS before IDAT > alpha verdict"""
    if len(data) < 33 or data[12:16] != b"IHDR":
        return {"error": "PNG without a valid IHDR chunk"}
    width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    has_transparency_chunk = False
    # Walk chunks: length(4) type(4) data CRC(4)
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
    """Walk markers > height·width of the first SOF (JPEG has no alpha)"""
    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            return {"error": "JPEG marker stream is broken"}
        marker = data[offset + 1]
        if marker == 0xFF:                       # fill byte
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
