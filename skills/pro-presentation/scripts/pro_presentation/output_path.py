"""get-output-path: default place for a new deck in this project"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit

from pro_presentation.settings import SKILL_ID


def cmd_output_path(args) -> int:
    """presentation/<date_number_title>/ under the output root (the deck carries its own .gitignore)"""
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
