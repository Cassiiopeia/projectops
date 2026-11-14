"""Postprocess in one pass: convert to PNG > check real transparency > remove background if needed > fit size > final facts
run handles everything so the user never sees intermediate steps; what was done is recorded only in steps
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import background, converter, image_facts, png_codec


def _ensure_png(source: Path, work_dir: Path, steps: list[str]) -> Path:
    facts = image_facts.read_facts(source)
    if facts.get("format") == "png":
        return source
    target = work_dir / (source.stem + ".png")
    tool = converter.to_png(source, target)
    steps.append(f"converted {facts.get('format')} to PNG ({tool})")
    return target


def _transparent_share(path: Path) -> float | None:
    """Share of fully transparent pixels (None if the PNG cannot be decoded)"""
    try:
        width, height, rgba = png_codec.read_rgba(path)
    except (png_codec.UnsupportedPng, OSError, ValueError):
        return None
    transparent = sum(1 for index in range(3, len(rgba), 4) if rgba[index] == 0)
    return transparent / (width * height)


def remove_background(source: Path, target: Path, key_color: str | None, tolerance: float, mode: str | None) -> dict:
    """One background removal > key, mode and transparent share used"""
    width, height, rgba = png_codec.read_rgba(source)
    keys = [background.parse_hex_color(key_color)] if key_color else background.detect_keys(width, height, rgba)
    if not keys:
        return {"ok": False, "code": "no_background_color", "summary": "Border has no dominant color to remove"}
    # Explicit key color uses global (including gaps between objects); auto-detect uses flood (only areas connected to the border)
    chosen_mode = mode or ("global" if key_color else "flood")
    stats = background.remove(width, height, rgba, keys, tolerance, chosen_mode)
    png_codec.write_rgba(target, width, height, rgba)
    return {"ok": True, "keys": ["#%02X%02X%02X" % key for key in keys], "mode": chosen_mode, **stats}


def finish(source: Path, final_path: Path, size: tuple[int, int], is_alpha_required: bool,
           key_color: str | None) -> dict:
    """Generated original > final PNG at the requested spec"""
    work_dir = final_path.parent / "work"
    work_dir.mkdir(exist_ok=True)
    steps: list[str] = []
    current = _ensure_png(source, work_dir, steps)
    if is_alpha_required:
        share = _transparent_share(current)
        # Almost no transparent pixels means fake transparency (checkerboard) or a solid background > remove background
        if share is None or share < 0.02:
            cleared = work_dir / "background_removed.png"
            if share is None:
                converter.to_png(current, cleared)
                current = cleared
            removal = remove_background(current, cleared, key_color, background.DEFAULT_TOLERANCE, None)
            if not removal["ok"]:
                return {"steps": steps, **removal}
            steps.append(f"removed background {removal['keys']} ({removal['mode']}, "
                         f"{round(removal['transparent_share'] * 100)}% transparent)")
            current = cleared
    facts = image_facts.read_facts(current)
    if (facts.get("width"), facts.get("height")) != size:
        # Transparent images (objects) use contain so nothing is cut; background images use cover so there are no gaps
        mode = "contain" if is_alpha_required else "cover"
        tool = converter.fit(current, work_dir / "fitted.png", size, mode)
        steps.append(f"resized {facts.get('width')}x{facts.get('height')} to {size[0]}x{size[1]} ({mode}, {tool})")
        current = work_dir / "fitted.png"
    if current != final_path:
        shutil.copyfile(current, final_path)
    return {"ok": True, "steps": steps}
