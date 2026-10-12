"""캡처를 둘 곳과 이름 · 줄이기. app 과 web 이 같은 규칙을 쓴다."""
from __future__ import annotations

import os
import time
from pathlib import Path

from common.image import SHOT_MAX_SIDE, WEBP_QUALITY, to_webp

from pro_launch.runtime.context import state_home


def shot_folder(root: Path) -> Path:
    """캡처를 둘 곳. env.sh 를 source 했으면 그 실행 폴더, 아니면 상태 폴더의 shots."""
    env_shot = os.environ.get("SHOT_DIR")
    d = Path(env_shot) if env_shot else state_home(root) / "shots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def shot_target(root: Path, name: str | None, ext: str = ".png") -> tuple[Path, bool]:
    """(저장 경로, 경로를 직접 줬는가). 이름만 주면 SHOT_DIR 아래에 둔다."""
    if name and (os.sep in name or "/" in name):
        p = Path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p, True
    stem = Path(name).stem if name else time.strftime("%Y%m%d-%H%M%S")
    return shot_folder(root) / f"{stem}{ext}", False


def finish_shot(raw: Path, explicit: bool, args) -> Path:
    """경로를 직접 줬거나 --keep-format 이면 그대로, 아니면 줄이고 WebP 로."""
    if explicit or getattr(args, "keep_format", False):
        return raw
    return to_webp(raw, quality=args.quality, max_side=args.max_side or None) or raw


def add_shot_args(p) -> None:
    # 세션 토큰은 해상도에서만 줄어든다. 0 을 주면 원본 크기 그대로 둔다.
    p.add_argument("--max-side", type=int, default=SHOT_MAX_SIDE,
                   help=f"긴 변 상한 (기본 {SHOT_MAX_SIDE}, 0이면 원본)")
    p.add_argument("--quality", type=int, default=WEBP_QUALITY,
                   help=f"WebP 품질 (기본 {WEBP_QUALITY})")
    p.add_argument("--keep-format", action="store_true",
                   help="PNG 원본 그대로 둔다 — 픽셀 대조처럼 원본이 필요할 때")
