"""캡처에 쓸 브라우저 고르기: pro-launch 규칙과 동일 (환경변수 > 번들 Chromium > 설치된 Chrome, Edge)
표준 라이브러리만 사용 (캡처 워커가 전용 가상환경 파이썬으로 직접 import)
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

# skills/pro-launch/scripts/browser_pick.py (이 파일: skills/pro-ui-design/scripts/pro_ui_design/)
BROWSER_PICK_FILE = Path(__file__).resolve().parents[3] / "pro-launch" / "scripts" / "browser_pick.py"


def _load_browser_pick():
    spec = importlib.util.spec_from_file_location("browser_pick", BROWSER_PICK_FILE)
    if spec is None or not BROWSER_PICK_FILE.is_file():
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_browser_executable(playwright) -> str | None:
    """실행 파일 경로. None 이면 Playwright 기본값에 맡김"""
    browser_pick = _load_browser_pick()
    if browser_pick is None:
        return None
    try:
        bundled = playwright.chromium.executable_path
    except Exception:  # Playwright 내부 오류: 번들 없음과 같게 처리
        bundled = None
    return browser_pick.resolve(bundled).get("exe")
