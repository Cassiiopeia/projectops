"""ascii: 박스 문자 와이어 (한글 두 칸 폭 보정)"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from common.emit import emit


# =========================================================================
# ascii — 등폭 · 박스 문자 · 한글 폭 보정
# =========================================================================

def text_width(s: str) -> int:
    """화면에 차지하는 칸 수. 한글·전각은 두 칸 — 안 세면 오른쪽 선이 어긋난다."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _fit(s: str, width: int, align: str) -> str:
    # s 가 비었는데 width 가 음수면 영원히 안 끝난다 — s 가 있을 때만 줄인다 (#709)
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
    """width 는 1 이상 정수만 받는다. 없으면 30. 아니면 ValueError (#709)."""
    raw = spec.get("width")
    if raw is None or raw == "":
        return 30
    if isinstance(raw, bool) or not isinstance(raw, (int, str)) \
            or (isinstance(raw, str) and not re.fullmatch(r"\s*-?\d+\s*", raw)):
        raise ValueError(f"width 는 1 이상 정수여야 합니다 ({raw!r})")
    n = int(raw)
    if n < 1:
        raise ValueError(f"width 는 1 이상 정수여야 합니다 ({raw!r})")
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
    except OSError:      # 긴 JSON 문자열은 파일 이름으로 쓸 수 없다
        is_file = False
    try:
        spec = json.loads(spec_f.read_text(encoding="utf-8")) if is_file else json.loads(args.spec)
    except (OSError, json.JSONDecodeError) as e:
        return emit({"ok": False, "code": "bad_spec", "error": str(e),
                     "next": "SKILL.md 의 ascii 스펙 {title, rows, width, caption} 형식으로 다시 준다"})
    if not isinstance(spec, dict):
        return emit({"ok": False, "code": "bad_spec",
                     "error": f"스펙은 JSON 객체여야 합니다 ({type(spec).__name__})",
                     "next": '예: {"width":24,"rows":["로그인"]}'})
    if not isinstance(spec.get("rows") or [], list):
        return emit({"ok": False, "code": "bad_spec", "error": "rows 는 배열이어야 합니다"})
    try:
        width = _ascii_width(spec)
    except ValueError as e:
        return emit({"ok": False, "code": "bad_spec", "error": str(e)})
    text = render_ascii(spec)
    body = text.split("\n")
    widths = {text_width(l) for l in body[:-1 if spec.get("caption") else None]}
    out = {"ascii": text, "width": width + 2, "aligned": len(widths) == 1,
           "summary": f"{len(body)}줄 와이어"}
    unknown = sorted(k for k in spec if k not in _ASCII_KEYS)
    if unknown:
        # 모르는 키는 조용히 무시되어 빈 박스만 나온다 — 알려 준다
        out["warnings"] = [f"모르는 키 {unknown} 는 무시했습니다 (쓸 수 있는 키: {', '.join(_ASCII_KEYS)})"]
    if args.out:
        try:
            out_f = Path(args.out)
            out_f.parent.mkdir(parents=True, exist_ok=True)
            out_f.write_text(text + "\n", encoding="utf-8")
        except OSError as e:
            return emit({"ok": False, "code": "write_failed", "error": str(e), "ascii": text})
        out["file"] = args.out
    return emit(out)
