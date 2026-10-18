"""이 호출을 낸 agent 세션 가르기 — web 탭 소유(#878) · 기기 소유(#925) 공용 원본.

세션은 LAUNCH_SESSION > CLAUDE_CODE_SESSION_ID 로 가른다. 둘 다 없으면 모든 세션이 같은 이름(anonymous)을 쓴다.
"""
from __future__ import annotations

import os

# 세션을 가르는 환경변수 (앞쪽 우선). 직접 주는 값 > Claude Code 가 세션마다 주는 값
SESSION_ENV_VARS = ("LAUNCH_SESSION", "CLAUDE_CODE_SESSION_ID")
ANONYMOUS_SESSION = "anonymous"


def session_identity() -> str:
    return next((os.environ[var].strip() for var in SESSION_ENV_VARS if (os.environ.get(var) or "").strip()),
                ANONYMOUS_SESSION)
