"""비교판: 후보 그림 여러 장 > 번호 붙은 한 장 (사용자가 번호로 고름)
Pillow 있으면 번호 글자 표시, 없으면 표준 라이브러리로 격자만 (번호는 왼쪽 위부터 순서)
"""
from __future__ import annotations

from pathlib import Path

from . import png_codec

# 칸 하나 크기 (픽셀), 칸 사이 여백, 바탕색 (투명 그림이 보이도록 중간 회색)
CELL_PIXELS = 512
GAP_PIXELS = 16
BOARD_COLOR = (58, 58, 64, 255)


def _columns(count: int) -> int:
    return 2 if count == 4 else min(count, 3)


def _pillow_modules():
    """Pillow (Image, ImageDraw), 없으면 None"""
    try:
        from PIL import Image, ImageDraw  # noqa: PLC0415 — 선택 의존성
    except ImportError:
        return None
    return Image, ImageDraw


def _build_with_pillow(images: list[Path], target: Path, Image, ImageDraw) -> None:
    columns = _columns(len(images))
    rows = (len(images) + columns - 1) // columns
    board = Image.new("RGBA", (columns * (CELL_PIXELS + GAP_PIXELS) + GAP_PIXELS,
                               rows * (CELL_PIXELS + GAP_PIXELS) + GAP_PIXELS), BOARD_COLOR)
    draw = ImageDraw.Draw(board)
    for position, path in enumerate(images):
        with Image.open(path) as image:
            image = image.convert("RGBA")
            image.thumbnail((CELL_PIXELS, CELL_PIXELS))
            left = GAP_PIXELS + (position % columns) * (CELL_PIXELS + GAP_PIXELS)
            top = GAP_PIXELS + (position // columns) * (CELL_PIXELS + GAP_PIXELS)
            board.alpha_composite(image, (left + (CELL_PIXELS - image.width) // 2,
                                          top + (CELL_PIXELS - image.height) // 2))
            draw.rectangle((left, top, left + 44, top + 36), fill=(0, 0, 0, 200))
            draw.text((left + 14, top + 8), str(position + 1), fill=(255, 255, 255, 255), font_size=24)
    board.save(target, "PNG")


def _build_with_stdlib(images: list[Path], target: Path) -> None:
    """최근접 축소 + 격자 배치 (PNG 입력만)"""
    columns = _columns(len(images))
    rows = (len(images) + columns - 1) // columns
    width = columns * (CELL_PIXELS + GAP_PIXELS) + GAP_PIXELS
    height = rows * (CELL_PIXELS + GAP_PIXELS) + GAP_PIXELS
    canvas = bytearray(bytes(BOARD_COLOR) * (width * height))
    for position, path in enumerate(images):
        source_width, source_height, rgba = png_codec.read_rgba(path)
        scale = min(CELL_PIXELS / source_width, CELL_PIXELS / source_height)
        cell_width, cell_height = int(source_width * scale), int(source_height * scale)
        left = GAP_PIXELS + (position % columns) * (CELL_PIXELS + GAP_PIXELS) + (CELL_PIXELS - cell_width) // 2
        top = GAP_PIXELS + (position // columns) * (CELL_PIXELS + GAP_PIXELS) + (CELL_PIXELS - cell_height) // 2
        for row in range(cell_height):
            source_row = int(row / scale)
            for column in range(cell_width):
                source_offset = (source_row * source_width + int(column / scale)) * 4
                alpha = rgba[source_offset + 3] / 255
                target_offset = ((top + row) * width + left + column) * 4
                for channel in range(3):
                    canvas[target_offset + channel] = round(rgba[source_offset + channel] * alpha
                                                            + canvas[target_offset + channel] * (1 - alpha))
    png_codec.write_rgba(target, width, height, canvas)


def build(images: list[Path], target: Path) -> str:
    """비교판 저장 > 사용한 방식 이름"""
    modules = _pillow_modules()
    if modules:
        _build_with_pillow(images, target, *modules)
        return "pillow"
    _build_with_stdlib(images, target)
    return "stdlib"
