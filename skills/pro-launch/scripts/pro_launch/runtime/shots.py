"""캡처를 둘 곳과 이름 · 줄이기. app 과 web 이 같은 규칙을 쓴다."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from common.image import SHOT_MAX_SIDE, WEBP_QUALITY, to_webp

from pro_launch.runtime.context import state_home

# get-output-path 가 남기는 이번 실행 폴더 기록: <상태 폴더>/last_run.json {"run_dir", "screenshots", "at"} (#931)
LAST_RUN_FILE = "last_run.json"
# 이 시간 안의 기록만 쓴다 — 며칠 전 실행 폴더에 오늘 캡처가 섞이지 않게 (12시간)
LAST_RUN_VALID_SECONDS = 12 * 60 * 60
# 캡처 자리의 출처 3개: env(SHOT_DIR) · last_run(최근 get-output-path) · state(상태 폴더 shots)
SHOT_DIR_SOURCES = ("env", "last_run", "state")


def record_last_run(root: Path, run_dir: Path, screenshots: Path) -> None:
    """get-output-path 가 부른다. 기록 실패는 명령을 막지 않는다."""
    target = state_home(root) / LAST_RUN_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"run_dir": str(run_dir), "screenshots": str(screenshots),
                                      "at": time.time()}), encoding="utf-8")
    except OSError:
        pass


def _last_run_screenshots(root: Path) -> Path | None:
    """유효한(12시간 안 · 실행 폴더가 남아 있는) 최근 실행의 screenshots 폴더."""
    try:
        data = json.loads((state_home(root) / LAST_RUN_FILE).read_text(encoding="utf-8"))
        is_fresh = time.time() - float(data.get("at") or 0) < LAST_RUN_VALID_SECONDS
        run_dir, screenshots = Path(data["run_dir"]), Path(data["screenshots"])
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    return screenshots if is_fresh and run_dir.is_dir() else None


def resolve_shot_folder(root: Path) -> tuple[Path, str]:
    """(캡처 자리, 출처). 순서: $SHOT_DIR > 최근 get-output-path 실행 폴더 > 상태 폴더 shots."""
    env_shot = os.environ.get("SHOT_DIR")
    if env_shot:
        return Path(env_shot), "env"
    last_run = _last_run_screenshots(root)
    if last_run is not None:
        return last_run, "last_run"
    return state_home(root) / "shots", "state"


def shot_dir_source(root: Path) -> str:
    """캡처 자리 출처 > "env" | "last_run" | "state" — 결과에 싣게 (env.sh 를 안 불렀는지 알린다)."""
    return resolve_shot_folder(root)[1]


def shot_folder(root: Path) -> Path:
    """캡처를 둘 곳 (resolve_shot_folder 의 자리). 없으면 만든다."""
    d = resolve_shot_folder(root)[0]
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
