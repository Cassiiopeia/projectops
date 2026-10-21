"""`shrink` — 이슈 첨부용으로 이미지를 줄인다."""
from __future__ import annotations

from pathlib import Path

from common.image import SHOT_MAX_SIDE, WEBP_QUALITY, shrink

from pro_launch.registry import Command
from pro_launch.runtime.output import out


def cmd_shrink(args) -> int:
    return out(shrink([Path(p) for p in args.paths], max_side=args.max_side,
                      quality=args.quality, keep_format=args.keep_format))


def configure_shrink(p) -> None:
    p.add_argument("paths", nargs="+")
    p.add_argument("--max-side", type=int, default=SHOT_MAX_SIDE,
                   help=f"Longest side cap (default {SHOT_MAX_SIDE}) — same as captures")
    p.add_argument("--quality", type=int, default=WEBP_QUALITY,
                   help=f"WebP quality (default {WEBP_QUALITY})")
    p.add_argument("--keep-format", action="store_true", help="Do not convert to WebP")


COMMANDS = [
    Command(name="shrink", help="Shrink images for issue attachments · WebP", run=cmd_shrink,
            configure=configure_shrink),
]
