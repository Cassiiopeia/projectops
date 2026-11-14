"""Board > per-topic PNG (Chromium downloaded by pro-launch)"""
from __future__ import annotations

import sys
from pathlib import Path

from common.state import venv_site_packages

from pro_ui_design.browser_path import find_browser_executable


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
    """One PNG per topic (section). Uses the browser picked by pro-launch rules — installs nothing."""
    sync_playwright = _require_playwright()
    if sync_playwright is None:
        return [], "browser_missing"
    files = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=find_browser_executable(pw))
            page = browser.new_page(viewport={"width": 1448, "height": 900}, device_scale_factor=scale)
            page.goto(html_file.resolve().as_uri())
            page.evaluate("document.fonts.ready")
            page.wait_for_function("[...document.images].every(i => i.complete)", timeout=30000)
            page.add_style_tag(content="nav{display:none!important}")   # The table of contents is not needed in the image
            for n, topic in enumerate(topics, 1):
                el = page.locator(f"section#{topic}")
                box = el.bounding_box()
                if not box:
                    continue
                f = out_dir / f"{n:02d}_{topic}.png"
                el.screenshot(path=str(f))
                files.append(str(f))
            browser.close()
    except Exception as e:  # Browser binary missing or launch blocked
        return files, f"browser_failed: {str(e).splitlines()[0][:200]}"
    return files, None


def _png_width(f: Path) -> int:
    with f.open("rb") as fh:
        head = fh.read(24)
    return int.from_bytes(head[16:20], "big") if head[:8] == b"\x89PNG\r\n\x1a\n" else 0
