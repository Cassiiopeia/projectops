"""pro-agent-test 구현 패키지 — QA 절차(detect · scenario · note · api · other).

진입점은 `scripts/e2e_cli.py` 다. 앱·웹·서버를 띄우고 찍는 능력은 pro-launch 에 있다.

이 파일은 import 경로만 맞춘다. 공용 층(`<repo>/scripts/common`)을 스크립트로 불리든 테스트가 import 하든 찾게 한다.

  launch_bridge   pro-launch 서브프로세스 호출 · 옮긴 명령 위임
  storage         기록 자리 · 시나리오 파일 찾기 · 전제 펼치기
  scenario_rules  시나리오 본보기 · 검증
  notes/          learned.json 읽기·쓰기 · 기억 싣기 · 화면 대상 · tidy
  commands/       서브커맨드별 cmd_* (detect · scenario · note · api · other)
"""
from __future__ import annotations

import sys
from pathlib import Path

# <repo>/scripts — 모든 스킬이 공유하는 common/ 이 있는 곳
COMMON_ROOT = Path(__file__).resolve().parents[4] / "scripts"

if str(COMMON_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_ROOT))
