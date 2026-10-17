"""보드 > 주제별 PNG (pro-launch 가 받아 둔 Chromium)"""
from __future__ import annotations

import sys
from pathlib import Path

from common.state import venv_site_packages


def _require_playwright():
    sp = venv_site_packages()
    if sp and str(sp) not in sys.path:
        sys.path.insert(0, str(sp))
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def shoot_topics(html_file: Path, out_dir: Path, topics: list[str], scale: int = 2) -> tuple[list[str], str | None]:
    """주제(섹션)마다 PNG 한 장. pro-launch 가 받아 둔 Chromium 을 쓴다 — 따로 설치하지 않는다."""
    sync_playwright = _require_playwright()
    if sync_playwright is None:
        return [], "browser_missing"
    files = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1448, "height": 900}, device_scale_factor=scale)
            page.goto(html_file.resolve().as_uri())
            page.evaluate("document.fonts.ready")
            page.wait_for_function("[...document.images].every(i => i.complete)", timeout=30000)
            page.add_style_tag(content="nav{display:none!important}")   # 목차는 그림에 필요 없다
            for n, topic in enumerate(topics, 1):
                el = page.locator(f"section#{topic}")
                box = el.bounding_box()
                if not box:
                    continue
                f = out_dir / f"{n:02d}_{topic}.png"
                el.screenshot(path=str(f))
                files.append(str(f))
            browser.close()
    except Exception as e:  # 브라우저 파일이 없거나 실행이 막힌 경우
        return files, f"browser_failed: {str(e).splitlines()[0][:200]}"
    return files, None


def _png_width(f: Path) -> int:
    with f.open("rb") as fh:
        head = fh.read(24)
    return int.from_bytes(head[16:20], "big") if head[:8] == b"\x89PNG\r\n\x1a\n" else 0
