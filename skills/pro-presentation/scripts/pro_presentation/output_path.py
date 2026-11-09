"""get-output-path: 이 프로젝트에서 새 덱을 둘 기본 자리"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit

from pro_presentation.settings import SKILL_ID


def cmd_output_path(args) -> int:
    """산출물 루트 아래 presentation/<날짜_번호_제목>/ (덱이 스스로 .gitignore 를 들고 다닌다)"""
    try:
        from common.paths import resolve_output_path
    except ImportError:
        return emit({"ok": False, "code": "common_not_found", "error": "scripts/common/paths.py not found"})
    result = resolve_output_path(SKILL_ID, args.title, root=args.root)
    if result.get("ok") is False:
        return emit(result)
    path = Path(result["path"])
    deck_dir = path.parent / path.stem
    return emit({"deck_dir": str(deck_dir), "output_root": result.get("output_root"),
                 "summary": f"Deck location {deck_dir}",
                 "next": f"start --deck \"{deck_dir}\" --title \"<talk title>\""})
