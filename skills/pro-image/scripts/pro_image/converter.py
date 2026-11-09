"""형식 변환·크기 맞춤: 변환은 Pillow > sips(macOS) > ImageMagick, 크기는 Pillow > 표준 라이브러리
fit 모드 2개: cover 비율 유지 후 넘치는 부분 가운데 기준 자르기, contain 비율 유지 후 투명 여백
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import png_codec, resample


def _pillow():
    try:
        from PIL import Image  # noqa: PLC0415 — 선택 의존성
    except ImportError:
        return None
    return Image


def available_tool() -> str:
    """JPEG·WebP 변환 도구 (PNG 만이면 표준 라이브러리로 충분)"""
    if _pillow():
        return "pillow"
    if shutil.which("sips"):
        return "sips"
    return "magick" if shutil.which("magick") else "stdlib-png-only"


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=120)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "conversion failed").strip()[-400:])


def to_png(source: Path, target: Path) -> str:
    """아무 형식 > 8비트 RGBA PNG > 사용한 도구 이름"""
    image_module = _pillow()
    if image_module:
        with image_module.open(source) as image:
            image.convert("RGBA").save(target, "PNG")
        return "pillow"
    if shutil.which("sips"):
        _run(["sips", "-s", "format", "png", str(source), "--out", str(target)])
        return "sips"
    if shutil.which("magick"):
        _run(["magick", str(source), "-depth", "8", f"PNG32:{target}"])
        return "magick"
    raise RuntimeError("no converter: install Pillow (pip install pillow) or ImageMagick")


def _cover_box(source_size: tuple[int, int], target_size: tuple[int, int]) -> tuple[int, int]:
    scale = max(target_size[0] / source_size[0], target_size[1] / source_size[1])
    return round(source_size[0] * scale), round(source_size[1] * scale)


def fit(source: Path, target: Path, size: tuple[int, int], mode: str) -> str:
    """크기 맞춤 > 사용한 도구 이름"""
    width, height = size
    image_module = _pillow()
    if image_module:
        with image_module.open(source) as image:
            image = image.convert("RGBA")
            if mode == "cover":
                resized = image.resize(_cover_box(image.size, size), image_module.LANCZOS)
                left, top = (resized.width - width) // 2, (resized.height - height) // 2
                resized.crop((left, top, left + width, top + height)).save(target, "PNG")
            else:
                image.thumbnail(size, image_module.LANCZOS)
                canvas = image_module.new("RGBA", size, (0, 0, 0, 0))
                canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
                canvas.save(target, "PNG")
        return "pillow"
    return _fit_stdlib(source, target, size, mode)


def _fit_stdlib(source: Path, target: Path, size: tuple[int, int], mode: str) -> str:
    """Pillow 없을 때: PNG 로 맞춘 뒤 표준 라이브러리 크기 조절 (JPEG·WebP 는 sips·ImageMagick 로 먼저 변환)"""
    png_source = source
    if source.read_bytes()[:8] != png_codec.PNG_SIGNATURE:
        png_source = target.with_name(target.stem + "_source.png")
        to_png(source, png_source)
    width, height, rgba = png_codec.read_rgba(png_source)
    if mode == "cover":
        box_width, box_height = _cover_box((width, height), size)
        scaled = resample.resize(width, height, rgba, box_width, box_height)
        left, top = (box_width - size[0]) // 2, (box_height - size[1]) // 2
        png_codec.write_rgba(target, size[0], size[1], resample.crop(box_width, scaled, left, top, size[0], size[1]))
    else:
        scale = min(size[0] / width, size[1] / height)
        fit_width, fit_height = max(1, round(width * scale)), max(1, round(height * scale))
        scaled = resample.resize(width, height, rgba, fit_width, fit_height)
        png_codec.write_rgba(target, size[0], size[1], resample.pad(fit_width, fit_height, scaled, size[0], size[1]))
    return "stdlib"
