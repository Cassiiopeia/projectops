"""후처리 한 번에: PNG 변환 > 진짜 투명 여부 확인 > 필요 시 배경 제거 > 크기 맞춤 > 최종 사실
사용자에게 중간 과정을 보이지 않도록 run 이 끝까지 처리하고, 한 일은 steps 로만 남김
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
    """완전 투명 픽셀 비율 (PNG 디코드 불가면 None)"""
    try:
        width, height, rgba = png_codec.read_rgba(path)
    except (png_codec.UnsupportedPng, OSError, ValueError):
        return None
    transparent = sum(1 for index in range(3, len(rgba), 4) if rgba[index] == 0)
    return transparent / (width * height)


def remove_background(source: Path, target: Path, key_color: str | None, tolerance: float, mode: str | None) -> dict:
    """배경 제거 1회 > 사용한 키·모드·투명 비율"""
    width, height, rgba = png_codec.read_rgba(source)
    keys = [background.parse_hex_color(key_color)] if key_color else background.detect_keys(width, height, rgba)
    if not keys:
        return {"ok": False, "code": "no_background_color", "summary": "Border has no dominant color to remove"}
    # 키 컬러를 지정했으면 global(물체 사이 틈까지), 자동 판별이면 flood(테두리와 이어진 곳만)
    chosen_mode = mode or ("global" if key_color else "flood")
    stats = background.remove(width, height, rgba, keys, tolerance, chosen_mode)
    png_codec.write_rgba(target, width, height, rgba)
    return {"ok": True, "keys": ["#%02X%02X%02X" % key for key in keys], "mode": chosen_mode, **stats}


def finish(source: Path, final_path: Path, size: tuple[int, int], is_alpha_required: bool,
           key_color: str | None) -> dict:
    """생성 원본 > 요청 규격의 최종 PNG"""
    work_dir = final_path.parent / "work"
    work_dir.mkdir(exist_ok=True)
    steps: list[str] = []
    current = _ensure_png(source, work_dir, steps)
    if is_alpha_required:
        share = _transparent_share(current)
        # 투명 픽셀이 거의 없으면 가짜 투명(체크무늬)·단색 배경 > 배경 제거
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
        # 투명 그림(물체)은 잘리지 않게 contain, 배경 그림은 빈틈 없게 cover
        mode = "contain" if is_alpha_required else "cover"
        tool = converter.fit(current, work_dir / "fitted.png", size, mode)
        steps.append(f"resized {facts.get('width')}x{facts.get('height')} to {size[0]}x{size[1]} ({mode}, {tool})")
        current = work_dir / "fitted.png"
    if current != final_path:
        shutil.copyfile(current, final_path)
    return {"ok": True, "steps": steps}
