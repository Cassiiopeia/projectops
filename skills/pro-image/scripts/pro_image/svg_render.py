"""SVG > PNG (claude-vector 경로): 설치된 Chrome·Edge·Chromium 헤드리스 스크린샷, 투명 배경 유지
브라우저 찾기 순서: PATH 의 명령 > OS별 기본 설치 경로 (macOS·Windows·Linux)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# PATH 에서 찾을 브라우저 명령
BROWSER_COMMANDS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "chrome",
                    "msedge")
# OS별 기본 설치 경로
BROWSER_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
)
RENDER_TIMEOUT_SECONDS = 60
PAGE_TEMPLATE = ("<!doctype html><html><head><meta charset='utf-8'><style>html,body{{margin:0;background:transparent;}}"
                 "img{{display:block;width:{width}px;height:{height}px;}}</style></head>"
                 "<body><img src='{source}'></body></html>")


def find_browser() -> str | None:
    for command in BROWSER_COMMANDS:
        found = shutil.which(command)
        if found:
            return found
    for candidate in BROWSER_PATHS:
        expanded = os.path.expandvars(candidate)
        if "%" not in expanded and Path(expanded).is_file():
            return expanded
    return None


def render(svg_path: Path, target: Path, size: tuple[int, int]) -> str:
    """SVG 를 지정 크기 PNG 로 > 사용한 브라우저 경로"""
    browser = find_browser()
    if not browser:
        raise RuntimeError("no Chrome, Edge or Chromium found to render SVG")
    with tempfile.TemporaryDirectory() as work_dir:
        page = Path(work_dir) / "render.html"
        page.write_text(PAGE_TEMPLATE.format(width=size[0], height=size[1], source=svg_path.resolve().as_uri()),
                        encoding="utf-8")
        command = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                   "--default-background-color=00000000", f"--window-size={size[0]},{size[1]}",
                   f"--user-data-dir={Path(work_dir) / 'profile'}", f"--screenshot={target.resolve()}", page.as_uri()]
        completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace",
                                   timeout=RENDER_TIMEOUT_SECONDS)
    if not target.is_file():
        raise RuntimeError(f"browser did not write the PNG: {(completed.stderr or '')[-300:]}")
    return browser
