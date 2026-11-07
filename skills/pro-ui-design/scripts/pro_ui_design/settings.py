"""요청서 공통 값: 스킬 id, 보드 템플릿 위치, 게시 방식, PNG 폭 상한"""
from __future__ import annotations

from pathlib import Path

SKILL_ID = "ui-design"
# skills/pro-ui-design/assets/board.html (이 파일: skills/pro-ui-design/scripts/pro_ui_design/)
_TEMPLATE = Path(__file__).resolve().parents[2] / "assets" / "board.html"
# 세션 폴더 안 이름 (server.py 는 표준 라이브러리 전용 실행이라 같은 값을 따로 둠)
SESSION_TOKENS_FILE_NAME = "tokens.css"
CAPTURES_FOLDER_NAME = "captures"
DESTINATIONS = ("issue", "html", "markdown")
# 한 장 폭 상한. GitHub 은 이보다 넓은 그림을 줄여 보여 글자가 안 읽힌다.
MAX_PNG_WIDTH = 3400
