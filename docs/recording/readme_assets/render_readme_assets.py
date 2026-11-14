"""README 이미지 렌더: 소스 HTML x 테마(light, dark) x 언어(en, ko) > docs/images/readme-*.webp (2배 해상도)
실행: python3 docs/recording/readme_assets/render_readme_assets.py [--only hero,cycle] [--lang en]
브라우저: pro-launch web setup 이 설치한 Playwright·Chromium (없으면 그 가상환경 파이썬으로 다시 실행)
이름: readme-<자산>.webp (en 라이트), readme-<자산>-dark.webp, 한국어는 .ko.webp
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SOURCE_DIR.parents[2]
OUTPUT_DIR = REPO_ROOT / "docs/images"
# 브라우저 고르기 규칙은 pro-ui-design 캡처와 같은 것을 씀 (환경변수 > 번들 Chromium > 설치된 Chrome)
BROWSER_PATH_DIR = REPO_ROOT / "skills/pro-ui-design/scripts/pro_ui_design"
COMMON_SCRIPTS_DIR = REPO_ROOT / "scripts"

ASSET_NAMES = ("hero", "cycle", "features", "skills")
THEMES = ("light", "dark")
LANGUAGES = ("en", "ko")
DEVICE_SCALE = 2
# 캔버스보다 넉넉한 창 (요소 스크린샷이라 실제 크기는 #canvas 가 정함)
VIEWPORT_WIDTH_PIXELS = 1400
VIEWPORT_HEIGHT_PIXELS = 1200
WEBP_QUALITY = 90
# 재실행 표식: 가상환경 파이썬으로 다시 띄운 뒤 또 다시 띄우지 않게
REEXEC_ENV_KEY = "README_ASSETS_REEXEC"


def ensure_playwright() -> None:
    """Playwright 없으면 pro-launch 가상환경 파이썬으로 같은 인자 재실행"""
    try:
        import playwright  # noqa: F401
        import PIL  # noqa: F401
        return
    except ImportError:
        pass
    if os.environ.get(REEXEC_ENV_KEY):
        raise SystemExit("Playwright or Pillow missing: run `launch_cli.py web setup` (pro-launch) first")
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))
    from common.state import venv_python

    interpreter = venv_python()
    if interpreter is None:
        raise SystemExit("No pro-launch browser environment: run `launch_cli.py web setup` first")
    completed = subprocess.run([str(interpreter), __file__, *sys.argv[1:]], env={**os.environ, REEXEC_ENV_KEY: "1"})
    raise SystemExit(completed.returncode)


def output_name(asset: str, theme: str, language: str) -> str:
    """hero, dark, ko > readme-hero-dark.ko.webp"""
    theme_part = "-dark" if theme == "dark" else ""
    language_part = "" if language == "en" else f".{language}"
    return f"readme-{asset}{theme_part}{language_part}.webp"


def render_one(page, asset: str, theme: str, language: str) -> Path:
    """소스 열기 > 글꼴 대기 > #canvas 투명 배경 스크린샷 > webp 저장"""
    from PIL import Image

    source_url = (SOURCE_DIR / f"{asset}.html").as_uri() + f"?theme={theme}&lang={language}"
    page.goto(source_url, wait_until="load")
    page.evaluate("document.fonts.ready")
    png_bytes = page.locator("#canvas").screenshot(omit_background=True, animations="disabled")
    target = OUTPUT_DIR / output_name(asset, theme, language)
    Image.open(io.BytesIO(png_bytes)).save(target, "WEBP", quality=WEBP_QUALITY, method=6)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the README images from their HTML sources")
    parser.add_argument("--only", default=",".join(ASSET_NAMES), help="Comma-separated asset names")
    parser.add_argument("--lang", default=",".join(LANGUAGES), help="Comma-separated languages")
    args = parser.parse_args()
    assets = [name for name in args.only.split(",") if name]
    languages = [name for name in args.lang.split(",") if name]
    unknown = [name for name in assets if name not in ASSET_NAMES] + [name for name in languages if name not in LANGUAGES]
    if unknown:
        raise SystemExit(f"Unknown asset or language: {', '.join(unknown)}")
    ensure_playwright()

    from playwright.sync_api import sync_playwright

    sys.path.insert(0, str(BROWSER_PATH_DIR))
    from browser_path import find_browser_executable

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=find_browser_executable(playwright))
        context = browser.new_context(viewport={"width": VIEWPORT_WIDTH_PIXELS, "height": VIEWPORT_HEIGHT_PIXELS},
                                      device_scale_factor=DEVICE_SCALE)
        page = context.new_page()
        # 자산 x 언어 x 테마 전부 (성공·실패 공통으로 브라우저 닫음)
        try:
            for asset in assets:
                for language in languages:
                    for theme in THEMES:
                        target = render_one(page, asset, theme, language)
                        print(f"wrote {target.relative_to(REPO_ROOT)} ({target.stat().st_size // 1024} KB)")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
