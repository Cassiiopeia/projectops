"""Shared request values: skill id, board template location, publishing mode, PNG width cap"""
from __future__ import annotations

from pathlib import Path

SKILL_ID = "ui-design"
# skills/pro-ui-design/assets/board.html (this file: skills/pro-ui-design/scripts/pro_ui_design/)
_TEMPLATE = Path(__file__).resolve().parents[2] / "assets" / "board.html"
# Names inside the session folder (server.py runs stdlib-only, so it keeps its own copy of these values)
SESSION_TOKENS_FILE_NAME = "tokens.css"
CAPTURES_FOLDER_NAME = "captures"
DESTINATIONS = ("issue", "html", "markdown")
# Width cap per image. GitHub shrinks wider images until text is unreadable.
MAX_PNG_WIDTH = 3400
