"""pro-ui-design 구현 패키지: 로컬 시안 세션 + 디자이너 요청서. 판단은 agent, 여기는 실행과 사실 수집만
진입점 scripts/ui_design_cli.py. 이 파일은 공용 common import 경로만 맞춤
"""
from __future__ import annotations

import sys
from pathlib import Path

# <repo>/scripts — 모든 스킬이 공유하는 common/ 이 있는 곳
COMMON_ROOT = Path(__file__).resolve().parents[4] / "scripts"

if str(COMMON_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_ROOT))
