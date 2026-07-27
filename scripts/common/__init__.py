"""common — cassiiopeia skill 공용 인프라.

3-layer 아키텍처의 Layer 1. 각 skill의 _cli.py가 이 패키지를 import한다.
순수 함수 + 단일 책임 모듈만 둔다. skill 의존성 0.
"""

__version__ = "1.0.0"

# 산출물 경로 생성 대상 skill_id 목록 (paths.py·기타에서 사용)
SUPPORTED_SKILL_IDS = [
    "analyze",
    "plan",
    "note",
    "report",
    "review",
    "testcase",
    "issue",
    "github",
    "synology-expose",
]
