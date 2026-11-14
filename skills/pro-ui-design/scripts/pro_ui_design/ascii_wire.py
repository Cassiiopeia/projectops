"""ascii: box-drawing wireframe (wide characters take two columns)"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from common.emit import emit


# =========================================================================
# ascii — monospace, box-drawing characters, wide-character width fix
# =========================================================================

def text_width(s: str) -> int:
    """Columns taken on screen. Hangul and full-width take two — otherwise the right border drifts."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _fit(s: str, width: int, align: str) -> str:
    # Empty s with negative width never ends — shrink only while s is non-empty (#709)
    while s and text_width(s) > width:
        s = s[:-1]
    gap = width - text_width(s)
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    if align == "right":
        return " " * gap + s
    return s + " " * gap


_ASCII_KEYS = ("title", "rows", "width", "caption")


def _ascii_width(spec: dict) -> int:
    """width must be an integer >= 1. Defaults to 30. Otherwise ValueError (#709)."""
    raw = spec.get("width")
    if raw is None or raw == "":
        return 30
    if isinstance(raw, bool) or not isinstance(raw, (int, str)) \
            or (isinstance(raw, str) and not re.fullmatch(r"\s*-?\d+\s*", raw)):
        raise ValueError(f"width must be an integer >= 1 ({raw!r})")
    n = int(raw)
    if n < 1:
        raise ValueError(f"width must be an integer >= 1 ({raw!r})")
    return n


def render_ascii(spec: dict) -> str:
    width = _ascii_width(spec)
    lines = ["┌" + "─" * width + "┐"]
    if spec.get("title"):
        lines.append("│" + _fit(" " + str(spec["title"]), width, "left") + "│")
        lines.append("├" + "─" * width + "┤")
    for row in spec.get("rows") or []:
        if row == "---":
            lines.append("├" + "─" * width + "┤")
            continue
        if isinstance(row, dict):
            text, align = str(row.get("text", "")), row.get("align", "left")
        else:
            text, align = str(row), "left"
        lines.append("│" + _fit(text, width, align) + "│")
    lines.append("└" + "─" * width + "┘")
    if spec.get("caption"):
        lines.append("  " + str(spec["caption"]))
    return "\n".join(lines)


def cmd_ascii(args) -> int:
    try:
        spec_f = Path(args.spec)
        is_file = spec_f.is_file()
    except OSError:      # A long JSON string cannot be used as a file name
        is_file = False
    try:
        spec = json.loads(spec_f.read_text(encoding="utf-8")) if is_file else json.loads(args.spec)
    except (OSError, json.JSONDecodeError) as e:
        return emit({"ok": False, "code": "bad_spec", "error": str(e),
                     "next": "Pass it again in the SKILL.md ascii spec format {title, rows, width, caption}"})
    if not isinstance(spec, dict):
        return emit({"ok": False, "code": "bad_spec",
                     "error": f"The spec must be a JSON object ({type(spec).__name__})",
                     "next": 'e.g. {"width":24,"rows":["Sign in"]}'})
    if not isinstance(spec.get("rows") or [], list):
        return emit({"ok": False, "code": "bad_spec", "error": "rows must be an array"})
    try:
        width = _ascii_width(spec)
    except ValueError as e:
        return emit({"ok": False, "code": "bad_spec", "error": str(e)})
    text = render_ascii(spec)
    body = text.split("\n")
    widths = {text_width(l) for l in body[:-1 if spec.get("caption") else None]}
    out = {"ascii": text, "width": width + 2, "aligned": len(widths) == 1,
           "summary": f"{len(body)}-line wireframe"}
    unknown = sorted(k for k in spec if k not in _ASCII_KEYS)
    if unknown:
        # Unknown keys are silently ignored and yield an empty box — report them
        out["warnings"] = [f"Ignored unknown keys {unknown} (allowed keys: {', '.join(_ASCII_KEYS)})"]
    if args.out:
        try:
            out_f = Path(args.out)
            out_f.parent.mkdir(parents=True, exist_ok=True)
            out_f.write_text(text + "\n", encoding="utf-8")
        except OSError as e:
            return emit({"ok": False, "code": "write_failed", "error": str(e), "ascii": text})
        out["file"] = args.out
    return emit(out)
