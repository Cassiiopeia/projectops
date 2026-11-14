"""Telling apart the agent session that made this call — single source shared by web tab ownership (#878) · device ownership (#925).

Sessions are told apart by LAUNCH_SESSION > CLAUDE_CODE_SESSION_ID. With neither, every session uses the same name (anonymous).
"""
from __future__ import annotations

import os

# Env vars that tell sessions apart (earlier wins). Value given directly > value Claude Code gives per session
SESSION_ENV_VARS = ("LAUNCH_SESSION", "CLAUDE_CODE_SESSION_ID")
ANONYMOUS_SESSION = "anonymous"


def session_identity() -> str:
    return next((os.environ[var].strip() for var in SESSION_ENV_VARS if (os.environ.get(var) or "").strip()),
                ANONYMOUS_SESSION)
