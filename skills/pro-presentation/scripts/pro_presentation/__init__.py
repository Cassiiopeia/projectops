"""pro-presentation 구현 패키지: HTML 덱 폴더 + 연습 서버 + 녹화·검사·내보내기. 판단(코칭·구간)은 agent
진입점 scripts/presentation_cli.py. 이 파일은 공용 common import 경로만 맞춤
"""
from __future__ import annotations

import sys
from pathlib import Path

# <repo>/scripts — 모든 스킬이 공유하는 common/ 이 있는 곳
COMMON_ROOT = Path(__file__).resolve().parents[4] / "scripts"

if str(COMMON_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_ROOT))
