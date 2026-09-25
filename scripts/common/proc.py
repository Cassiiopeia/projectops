"""외부 명령 실행과 Android SDK 도구 찾기 (pro-launch · pro-agent-test 공용, #629).

두 CLI 가 같은 일을 각자 들고 있으면 한쪽만 고쳐져 어긋난다. 여기 한 곳에 둔다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], timeout: int = 15) -> str:
    """외부 명령 실행. 실패해도 예외를 올리지 않는다 —
    기기가 없거나 도구가 미설치인 상황이 정상 경로이기 때문이다."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def sdk_tool(name: str) -> str | None:
    """Android SDK 도구 경로. PATH에 없으면 표준 설치 위치를 본다.

    adb·emulator는 SDK를 설치해도 PATH에 자동 등록되지 않는 경우가 많다.
    여기서 찾아주지 않으면 기기가 있는데도 "없음"으로 보고하게 된다.
    """
    found = shutil.which(name)
    if found:
        return found

    # Windows 실행 파일은 확장자가 붙는다. Git Bash에서도 마찬가지다.
    exe = f"{name}.exe" if sys.platform == "win32" else name

    roots = [Path.home() / "Library" / "Android" / "sdk",   # macOS 기본
             Path.home() / "Android" / "Sdk"]               # Linux 기본
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT", "LOCALAPPDATA"):
        v = os.environ.get(env)
        if not v:
            continue
        base = Path(v)
        roots.append(base / "Android" / "Sdk" if env == "LOCALAPPDATA" else base)

    for root in roots:
        for sub in ("platform-tools", "emulator", "cmdline-tools/latest/bin"):
            cand = root / sub / exe
            if cand.exists():
                return str(cand)
    return None
