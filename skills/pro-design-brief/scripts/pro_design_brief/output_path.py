"""get-output-path: 이번 요청서 자리(run_dir · board_dir · brief.md)"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit

from pro_design_brief.settings import SKILL_ID


# =========================================================================
# get-output-path
# =========================================================================

def cmd_output_path(args) -> int:
    """이번 요청서 자리. 캡처는 pro-launch get-output-path --skill design-brief 로 같은 우산에 받는다."""
    try:
        from common.paths import resolve_output_path
    except ImportError:
        return emit({"ok": False, "code": "common_not_found",
                     "error": "scripts/common/paths.py 를 찾지 못했습니다"})
    r = resolve_output_path(SKILL_ID, args.title)
    if r.get("ok") is False:
        return emit(r)
    md = Path(r["path"])
    run_dir = md.parent / md.stem
    (run_dir / "board").mkdir(parents=True, exist_ok=True)
    return emit({"run_dir": str(run_dir), "board_dir": str(run_dir / "board"),
                 "brief_md": str(run_dir / "brief.md"), "gitignore": r.get("gitignore"),
                 "output_root": r.get("output_root"),
                 "summary": f"요청서 자리 {run_dir} (추적 제외 {r.get('gitignore')})",
                 "next": ("캡처는 pro-launch 로 받는다: launch_cli.py get-output-path --skill design-brief "
                          "(같은 제목) → 받은 env.sh 를 source 하면 $SHOT_DIR 가 이 우산 아래다")})
