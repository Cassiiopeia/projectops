"""pro-design-brief 구현 패키지 — 디자이너에게 넘길 요청서(보드) 조립.

진입점은 `scripts/design_brief_cli.py` 다. 이 파일은 import 경로만 맞춘다
(공용 층 `<repo>/scripts/common` 을 스크립트로 불리든 테스트가 import 하든 찾게 한다).

  settings        스킬 id · 템플릿 위치 · PNG 폭 상한
  config          config show|set (설정 해석 · 저장)
  output_path     get-output-path
  board           board 명령 (board_html · board_capture · board_markdown 조합)
  copy_lint       copy-lint
  ascii_wire      ascii
"""
from __future__ import annotations

import sys
from pathlib import Path

# <repo>/scripts — 모든 스킬이 공유하는 common/ 이 있는 곳
COMMON_ROOT = Path(__file__).resolve().parents[4] / "scripts"

if str(COMMON_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_ROOT))
