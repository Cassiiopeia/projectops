"""svg-check: downloaded SVG assets > find elements renderers drop (filter · style · text · gradientTransform)

flutter_svg does not draw these and only logs a console warning (`unhandled element`). Nobody read the warnings, so
glowing stars shipped as hard bands and external SVGs as black silhouettes (elum #297 · #469).
"""
from __future__ import annotations

import re
from pathlib import Path

from common.emit import emit

# Element > what happens in the renderer (only those with measured evidence)
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
