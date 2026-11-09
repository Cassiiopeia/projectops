"""PNG 읽기·쓰기 (표준 라이브러리 zlib): 8비트·비인터레이스 > RGBA 픽셀 바이트
지원 색 형식 4개: 0 회색, 2 RGB, 4 회색+알파, 6 RGBA (팔레트·16비트·인터레이스는 미지원 > 변환 도구로 우회)
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# 색 형식 > 픽셀당 채널 수
CHANNELS_BY_COLOR_TYPE = {0: 1, 2: 3, 4: 2, 6: 4}


class UnsupportedPng(ValueError):
    pass


def _chunks(data: bytes):
    position = len(PNG_SIGNATURE)
    while position < len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        yield kind, data[position + 8:position + 8 + length]
        position += 12 + length


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_distance, up_distance, corner_distance = abs(estimate - left), abs(estimate - up), abs(estimate - up_left)
    if left_distance <= up_distance and left_distance <= corner_distance:
        return left
    return up if up_distance <= corner_distance else up_left


def _unfilter(raw: bytes, width: int, height: int, channels: int) -> bytearray:
    """행별 필터 5종(None·Sub·Up·Average·Paeth) 복원"""
    stride = width * channels
    pixels = bytearray(stride * height)
    previous = bytearray(stride)
    position = 0
    for row in range(height):
        filter_type = raw[position]
        line = bytearray(raw[position + 1:position + 1 + stride])
        position += 1 + stride
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            up = previous[index]
            if filter_type == 1:
                line[index] = (line[index] + left) & 0xFF
            elif filter_type == 2:
                line[index] = (line[index] + up) & 0xFF
            elif filter_type == 3:
                line[index] = (line[index] + ((left + up) >> 1)) & 0xFF
            elif filter_type == 4:
                up_left = previous[index - channels] if index >= channels else 0
                line[index] = (line[index] + _paeth(left, up, up_left)) & 0xFF
        pixels[row * stride:(row + 1) * stride] = line
        previous = line
    return pixels


def _to_rgba(pixels: bytearray, color_type: int) -> bytearray:
    if color_type == 6:
        return pixels
    rgba = bytearray()
    channels = CHANNELS_BY_COLOR_TYPE[color_type]
    for index in range(0, len(pixels), channels):
        if color_type == 2:
            rgba += pixels[index:index + 3] + b"\xff"
        elif color_type == 0:
            rgba += bytes((pixels[index],) * 3) + b"\xff"
        else:
            rgba += bytes((pixels[index],) * 3) + bytes((pixels[index + 1],))
    return rgba


def read_rgba(path: Path) -> tuple[int, int, bytearray]:
    """PNG > (너비, 높이, RGBA 바이트)"""
    data = path.read_bytes()
    if data[:8] != PNG_SIGNATURE:
        raise UnsupportedPng("not a PNG file")
    header, compressed = None, bytearray()
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            compressed += body
    if header is None:
        raise UnsupportedPng("missing IHDR")
    width, height, bit_depth, color_type, _, _, interlace = header
    if bit_depth != 8 or interlace != 0 or color_type not in CHANNELS_BY_COLOR_TYPE:
        raise UnsupportedPng(f"bit depth {bit_depth}, color type {color_type}, interlace {interlace}")
    pixels = _unfilter(zlib.decompress(bytes(compressed)), width, height, CHANNELS_BY_COLOR_TYPE[color_type])
    return width, height, _to_rgba(pixels, color_type)


def write_rgba(path: Path, width: int, height: int, rgba: bytes) -> None:
    """RGBA 바이트 > PNG (필터 0, 압축 6)"""
    stride = width * 4
    raw = b"".join(b"\x00" + bytes(rgba[row * stride:(row + 1) * stride]) for row in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(PNG_SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6))
                     + chunk(b"IEND", b""))
