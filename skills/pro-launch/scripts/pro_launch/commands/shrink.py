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
                   help=f"긴 변 상한 (기본 {SHOT_MAX_SIDE}) — 캡처와 같은 기준")
    p.add_argument("--quality", type=int, default=WEBP_QUALITY,
                   help=f"WebP 품질 (기본 {WEBP_QUALITY})")
    p.add_argument("--keep-format", action="store_true", help="WebP 로 바꾸지 않는다")


COMMANDS = [
    Command(name="shrink", help="이슈 첨부용으로 이미지 축소 · WebP", run=cmd_shrink,
            configure=configure_shrink),
]
