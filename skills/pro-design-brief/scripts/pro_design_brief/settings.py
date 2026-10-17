"""요청서 공통 값: 스킬 id, 보드 템플릿 위치, 게시 방식, PNG 폭 상한"""
from __future__ import annotations

from pathlib import Path

SKILL_ID = "design-brief"
# skills/pro-design-brief/assets/board.html (이 파일: skills/pro-design-brief/scripts/pro_design_brief/)
_TEMPLATE = Path(__file__).resolve().parents[2] / "assets" / "board.html"
DESTINATIONS = ("issue", "html", "markdown")
# 한 장 폭 상한. GitHub 은 이보다 넓은 그림을 줄여 보여 글자가 안 읽힌다.
MAX_PNG_WIDTH = 3400
