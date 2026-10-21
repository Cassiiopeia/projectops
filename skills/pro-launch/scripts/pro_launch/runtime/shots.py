"""캡처를 둘 곳과 이름 · 줄이기. app 과 web 이 같은 규칙을 쓴다."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from common.image import SHOT_MAX_SIDE, WEBP_QUALITY, to_webp

from pro_launch.runtime.context import state_home
from pro_launch.runtime.output import add_response_fields
from pro_launch.runtime.session_identity import session_identity

# get-output-path 가 남기는 실행 폴더 기록: <상태 폴더>/last_run.json {"sessions": {세션: {run_dir, screenshots, at}}} (#931)
# 세션별로 둔다 — 레포 하나에 기록 하나면 다른 세션의 실행 폴더에 캡처가 섞였다 (#972)
LAST_RUN_FILE = "last_run.json"
# 이 시간 안의 기록만 쓴다 — 며칠 전 실행 폴더에 오늘 캡처가 섞이지 않게 (12시간)
LAST_RUN_VALID_SECONDS = 12 * 60 * 60
# 캡처 자리의 출처 3개: env(SHOT_DIR) · last_run(이 세션의 최근 get-output-path) · state(상태 폴더 shots)
SHOT_DIR_SOURCES = ("env", "last_run", "state")


def _read_last_runs(root: Path) -> dict:
    """{세션: 기록}. 세션 키가 없는 옛 모양(한 건)은 누구 것인지 몰라 버린다."""
    try:
        data = json.loads((state_home(root) / LAST_RUN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    sessions = data.get("sessions") if isinstance(data, dict) else None
    return {k: v for k, v in sessions.items() if isinstance(v, dict)} if isinstance(sessions, dict) else {}


def record_last_run(root: Path, run_dir: Path, screenshots: Path) -> None:
    """get-output-path 가 부른다 — 이 세션 칸만 바꾼다. 기록 실패는 명령을 막지 않는다."""
    target = state_home(root) / LAST_RUN_FILE
    sessions = _read_last_runs(root)
    now = time.time()
    sessions = {k: v for k, v in sessions.items() if now - float(v.get("at") or 0) < LAST_RUN_VALID_SECONDS}
    sessions[session_identity()] = {"run_dir": str(run_dir), "screenshots": str(screenshots), "at": now}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"sessions": sessions}), encoding="utf-8")
    except OSError:
        pass


def _fresh_run(row: dict) -> Path | None:
    """유효한(12시간 안 · 실행 폴더가 남아 있는) 기록의 screenshots 폴더."""
    try:
        is_fresh = time.time() - float(row.get("at") or 0) < LAST_RUN_VALID_SECONDS
        run_dir, screenshots = Path(row["run_dir"]), Path(row["screenshots"])
    except (ValueError, TypeError, KeyError):
        return None
    return screenshots if is_fresh and run_dir.is_dir() else None


def _last_run_screenshots(root: Path) -> Path | None:
    """이 세션의 최근 실행 screenshots 폴더. 다른 세션 것만 있으면 쓰지 않고 응답에 경고를 싣는다."""
    sessions = _read_last_runs(root)
    own = sessions.get(session_identity())
    if own is not None and (folder := _fresh_run(own)) is not None:
        return folder
    if any(_fresh_run(row) is not None for name, row in sessions.items() if name != session_identity()):
        add_response_fields({"shot_dir_note": "최근 get-output-path 는 다른 세션의 실행이라 그 폴더에 쓰지 않았다 — "
                                              "이 세션에서 get-output-path 를 부르고 source env.sh 한다"})
    return None


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
        # 확장자가 없으면 붙인다 — 브라우저 캡처가 unsupported mime type 으로 실패한다 (#972)
        if not p.suffix:
            p = p.with_name(p.name + ext)
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
