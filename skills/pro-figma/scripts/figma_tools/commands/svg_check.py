"""svg-check: 받은 SVG 에셋 > 렌더러가 버리는 요소 찾기 (filter · style · text · gradientTransform)

flutter_svg 는 이 요소를 그리지 않고 콘솔 경고(`unhandled element`)만 남긴다. 아무도 경고를 안 읽어
후광 별이 선명한 띠로, 외부 SVG 가 검은 실루엣으로 배포됐다 (elum #297 · #469).
"""
from __future__ import annotations

import re
from pathlib import Path

from common.emit import emit

# 요소 > 렌더러에서 생기는 일 (실측 근거가 있는 것만)
RISKY_FEATURES = {
    "filter": "blur, glow and shadow baked into the SVG are dropped",
    "style": "CSS in <style> is ignored, so fills fall back to black",
    "text": "text inside the SVG is not drawn",
    "gradientTransform": "the gradient is drawn without its transform (wrong direction or size)",
}
_ELEMENT_PATTERN = {name: re.compile(rf"<{name}[\s>/]") for name in ("filter", "style", "text")}
_ATTRIBUTE_PATTERN = {"gradientTransform": re.compile(r"\bgradientTransform\s*=")}


def _features_in(svg_text: str) -> list[str]:
    found = [name for name, pattern in _ELEMENT_PATTERN.items() if pattern.search(svg_text)]
    found += [name for name, pattern in _ATTRIBUTE_PATTERN.items() if pattern.search(svg_text)]
    return found


def cmd_svg_check(args) -> int:
    folder = Path(args.dir)
    if not folder.is_dir():
        return emit({"ok": False, "code": "dir_not_found", "error": f"Folder not found: {args.dir}"})
    files = sorted(folder.rglob("*.svg"))
    risky = []
    for svg in files:
        try:
            features = _features_in(svg.read_text(encoding="utf-8", errors="replace"))
        except OSError as error:
            risky.append({"file": str(svg), "error": str(error)})
            continue
        if features:
            risky.append({"file": str(svg), "features": features,
                          "effects": [RISKY_FEATURES[name] for name in features]})
    return emit({
        "dir": str(folder), "svg_count": len(files), "risky_count": len(risky), "risky": risky,
        "summary": f"{len(risky)} of {len(files)} SVG file(s) use features renderers often drop",
        "next": ("First check whether the project's loader already handles the feature (e.g. inlines <style> "
                 "at load). Otherwise export that node as PNG at the device scale (keeps the baked effect), "
                 "or remove the feature and draw it in code. Either way, render once and look at it"
                 if risky else "No risky SVG features. Still render each asset once and look at it"),
    })
