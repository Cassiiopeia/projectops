"""`mask` · `redact` — 이슈에 올리기 전 가리기. 무엇을 가릴지는 에이전트가 정하고, 원본은 그대로 둔다"""
from __future__ import annotations

import re
from pathlib import Path

from common.image import ImageMaskError, mask_regions
from common.redact import redact_text

from pro_launch.registry import Command
from pro_launch.runtime.output import out

RECT_PATTERN = re.compile(r"^(\d+),(\d+),(\d+),(\d+)$")
NEXT_AFTER_MASK = "Open the masked file with Read and confirm it is covered, then upload that file, not the original"
NEXT_AFTER_REDACT = ("This catches known formats only: read the result yourself for names, internal hosts and other "
                     "private details before quoting it")


def _resolve_input(raw: str, root: str | None) -> Path:
    """상대 경로는 --root 기준 (셸 폴더가 바뀐 뒤에도 같은 파일)"""
    path = Path(raw).expanduser()
    return Path(root).expanduser() / path if root and not path.is_absolute() else path


def _derive_output_path(source: Path, tag: str) -> Path:
    return source.with_name(f"{source.stem}.{tag}{source.suffix}")


def _parse_rects(raw_rects: list[str]) -> list[list[int]] | None:
    rects = []
    for raw in raw_rects:
        match = RECT_PATTERN.match(raw.strip())
        if not match:
            return None
        x, y, width, height = (int(value) for value in match.groups())
        if width <= 0 or height <= 0:
            return None
        rects.append([x, y, width, height])
    return rects


def cmd_mask(args) -> int:
    source = _resolve_input(args.image, args.root)
    if not source.is_file():
        return out({"ok": False, "code": "file_not_found", "error": f"No such file: {source}"})
    rects = _parse_rects(args.rect)
    if not rects:
        return out({"ok": False, "code": "bad_rect", "error": "Use --rect x,y,width,height in image pixels, width and height above 0"})
    target = Path(args.out).expanduser() if args.out else _derive_output_path(source, "masked")
    try:
        size = mask_regions(source, rects, target)
    except ImageMaskError as error:
        failure = {"ok": False, "code": error.code, "error": str(error)}
        if error.code == "pillow_missing":
            failure["next"] = "Ask the user, then run web setup (it installs Pillow)"
        return out(failure)
    return out({"ok": True, "code": "ok", "path": str(target), **size, "rects": len(rects),
                "summary": f"Covered {len(rects)} area(s): {target.name}", "next": NEXT_AFTER_MASK})


def cmd_redact(args) -> int:
    source = _resolve_input(args.path, args.root)
    if not source.is_file():
        return out({"ok": False, "code": "file_not_found", "error": f"No such file: {source}"})
    text, counts = redact_text(source.read_bytes().decode("utf-8", errors="replace"))
    target = Path(args.out).expanduser() if args.out else _derive_output_path(source, "redacted")
    target.write_text(text, encoding="utf-8")
    return out({"ok": True, "code": "ok", "path": str(target), "counts": counts,
                "summary": f"Replaced {sum(counts.values())} value(s): {target.name}", "next": NEXT_AFTER_REDACT})


def configure_mask(p) -> None:
    p.add_argument("image")
    p.add_argument("--rect", action="append", required=True, help="x,y,width,height in image pixels (repeatable)")
    p.add_argument("--out", default=None, help="Output file (default: <name>.masked<ext>)")
    p.add_argument("--root", default=None, help="Project root for relative paths")


def configure_redact(p) -> None:
    p.add_argument("path")
    p.add_argument("--out", default=None, help="Output file (default: <name>.redacted<ext>)")
    p.add_argument("--root", default=None, help="Project root for relative paths")


COMMANDS = [
    Command(name="mask", help="Cover areas of an image before posting; writes a new file", run=cmd_mask, configure=configure_mask),
    Command(name="redact", help="Replace known secrets and personal data in a text file; writes a new file", run=cmd_redact,
            configure=configure_redact),
]
