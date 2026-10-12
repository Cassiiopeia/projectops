"""pro-launch 구현 패키지 — 앱·웹·서버를 띄우고, 조작하고, 찍는다.

진입점은 `scripts/launch_cli.py` 다. 어디에 무엇이 있는지는 같은 폴더의 `ARCHITECTURE.md`.

이 파일은 import 경로만 맞춘다. 같은 스킬의 보조 모듈(credentials · knowledge · stealth …)과
공용 층(`<repo>/scripts/common`)을 스크립트로 불리든 테스트가 import 하든 찾게 한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
# skills/pro-launch/scripts — 보조 모듈이 있는 곳
SCRIPTS_DIR = _HERE.parent.parent
# <repo>/scripts — 모든 스킬이 공유하는 common/ 이 있는 곳
COMMON_ROOT = _HERE.parents[4] / "scripts"

for _p in (COMMON_ROOT, SCRIPTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
