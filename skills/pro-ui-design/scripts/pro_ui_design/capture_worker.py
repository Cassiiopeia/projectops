"""캡처 실행기: 작업 JSON > 브라우저로 PNG, GIF 저장 > 결과 JSON 출력
pro-launch 가상환경 파이썬으로 실행 (Playwright, Pillow 는 시스템 파이썬에 없을 수 있음)
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.parse
from pathlib import Path

from browser_path import find_browser_executable

KEY_HEADER = "X-UI-Design-Key"
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 900
MAX_VIEWPORT_HEIGHT = 1600
PNG_SCALE = 2
GIF_SCALE = 1
GIF_COLORS = 128
GIF_LAST_FRAME_HOLD_MILLISECONDS = 1200
GIF_MINIMUM_FRAME_MILLISECONDS = 20
GIF_REGION_SELECTORS = (".ui-screens", ".ui-options")
GIF_REGION_PADDING_PIXELS = 12
DRAG_MOVE_STEPS = 8
STEP_TIMEOUT_MILLISECONDS = 4000
DEFAULT_STEP_HOLD_MILLISECONDS = 500


class CaptureFailure(Exception):
    def __init__(self, code: str, **details):
        super().__init__(code)
        self.payload = {"ok": False, "code": code, **details}


def build_screen_url(job: dict) -> str:
    query = urllib.parse.urlencode({key: job[key] for key in ("device", "theme", "speed") if job.get(key)})
    return f"http://127.0.0.1:{job['port']}/screens/{urllib.parse.quote(job['screen'])}" + (f"?{query}" if query else "")


def open_screen(browser, job: dict, scale: int):
    context = browser.new_context(viewport={"width": job.get("width") or VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                                  device_scale_factor=scale, extra_http_headers={KEY_HEADER: job["key"]})
    page = context.new_page()
    page.goto(build_screen_url(job), wait_until="load")
    page.evaluate("document.fonts.ready")
    page.wait_for_function("[...document.images].every(i => i.complete)", timeout=30000)
    return page


def output_path(job: dict, suffix: str, extension: str) -> Path:
    """이름: 시안__안__기기__테마.확장자 (지정한 값만)"""
    parts = [Path(job["screen"]).stem, suffix, job.get("device"), job.get("theme")]
    return Path(job["out_dir"]) / ("__".join(part for part in parts if part) + extension)


def describe_file(path: Path, job: dict) -> dict:
    return {"path": str(path), "size_bytes": path.stat().st_size, "source_url": f"/screens/{job['screen']}"}


def capture_png(browser, job: dict) -> list[dict]:
    page = open_screen(browser, job, PNG_SCALE)
    if job.get("all_options"):
        option_ids = page.evaluate("[...new Set([...document.querySelectorAll('.ui-option [data-choice]')].map(e => e.dataset.choice))]")
        if not option_ids:
            raise CaptureFailure("option_not_found", error="No .ui-option cards with data-choice in this mockup")
    elif job.get("option"):
        option_ids = [job["option"]]
    else:
        path = output_path(job, "", ".png")
        page.screenshot(path=str(path), full_page=True)
        return [describe_file(path, job)]
    files = []
    for option_id in option_ids:
        card = page.locator(f".ui-option:has([data-choice={json.dumps(str(option_id))}])").first
        if card.count() == 0:
            raise CaptureFailure("option_not_found", error=f"No option {option_id} in this mockup")
        path = output_path(job, str(option_id), ".png")
        card.screenshot(path=str(path))
        files.append(describe_file(path, job))
    return files


class GifRecorder:
    """프레임 수집: 스크린샷 + 실제 시각 (재생 속도를 실제 시간에 맞춤)"""

    def __init__(self, page, clip: dict | None, max_frames: int):
        self.page, self.clip, self.max_frames = page, clip, max_frames
        self.frames: list[tuple[float, bytes]] = []
        self.is_truncated = False

    def shoot(self) -> None:
        if len(self.frames) >= self.max_frames:
            self.is_truncated = True
            return
        self.frames.append((time.monotonic(), self.page.screenshot(clip=self.clip) if self.clip else self.page.screenshot()))

    def hold(self, milliseconds: int) -> None:
        deadline = time.monotonic() + milliseconds / 1000
        self.shoot()
        while time.monotonic() < deadline:
            if self.is_truncated:
                time.sleep(max(0, deadline - time.monotonic()))
                return
            self.shoot()


def _find_recording_region(page) -> dict | None:
    """움직임이 보이는 영역만: 용량 절약. 없으면 화면 전체"""
    scroll_height = page.evaluate("document.documentElement.scrollHeight")
    viewport = page.viewport_size
    page.set_viewport_size({"width": viewport["width"], "height": min(max(scroll_height, VIEWPORT_HEIGHT), MAX_VIEWPORT_HEIGHT)})
    for selector in GIF_REGION_SELECTORS:
        box = page.locator(selector).first.bounding_box() if page.locator(selector).count() else None
        if box:
            x, y = max(0, box["x"] - GIF_REGION_PADDING_PIXELS), max(0, box["y"] - GIF_REGION_PADDING_PIXELS)
            return {"x": x, "y": y, "width": box["width"] + GIF_REGION_PADDING_PIXELS * 2,
                    "height": box["height"] + GIF_REGION_PADDING_PIXELS * 2}
    return None


def _center_of(page, selector: str) -> tuple[float, float]:
    locator = page.locator(selector).first
    locator.wait_for(state="visible", timeout=STEP_TIMEOUT_MILLISECONDS)
    box = locator.bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def run_step(page, recorder: GifRecorder, step: dict) -> None:
    action = step["action"]
    hold_milliseconds = step.get("ms", DEFAULT_STEP_HOLD_MILLISECONDS)
    if action == "click":
        page.locator(step["selector"]).first.click(timeout=STEP_TIMEOUT_MILLISECONDS)
    elif action == "press":
        x, y = _center_of(page, step["selector"])
        page.mouse.move(x, y)
        page.mouse.down()
        recorder.hold(hold_milliseconds)
        page.mouse.up()
        recorder.shoot()
        return
    elif action == "drag":
        x, y = _center_of(page, step["selector"])
        page.mouse.move(x, y)
        page.mouse.down()
        for index in range(1, DRAG_MOVE_STEPS + 1):
            page.mouse.move(x + step.get("dx", 0) * index / DRAG_MOVE_STEPS, y + step.get("dy", 0) * index / DRAG_MOVE_STEPS)
            recorder.shoot()
        page.mouse.up()
    elif action == "play":
        page.evaluate("id => UIDesign.play(id)", str(step["option"]))
    elif action == "play-all":
        page.evaluate("UIDesign.playAll()")
    elif action == "reset":
        page.evaluate("UIDesign.reset()")
    recorder.hold(hold_milliseconds)


def save_gif(recorder: GifRecorder, path: Path, max_width: int) -> None:
    from PIL import Image

    timestamps = [stamp for stamp, _ in recorder.frames]
    durations = [max(GIF_MINIMUM_FRAME_MILLISECONDS, int((later - earlier) * 1000))
                 for earlier, later in zip(timestamps, timestamps[1:])] + [GIF_LAST_FRAME_HOLD_MILLISECONDS]
    images = []
    for _, png in recorder.frames:
        image = Image.open(io.BytesIO(png)).convert("RGB")
        if image.width > max_width:
            image = image.resize((max_width, round(image.height * max_width / image.width)), Image.LANCZOS)
        images.append(image.convert("P", palette=Image.ADAPTIVE, colors=GIF_COLORS))
    images[0].save(path, save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=False, disposal=1)


def capture_gif(browser, job: dict) -> list[dict]:
    from playwright.sync_api import Error as PlaywrightError

    page = open_screen(browser, job, GIF_SCALE)
    recorder = GifRecorder(page, _find_recording_region(page), job["max_frames"])
    recorder.shoot()
    for index, step in enumerate(job["steps"]):
        try:
            run_step(page, recorder, step)
        except PlaywrightError as error:
            raise CaptureFailure("step_failed", step_index=index, step=step,
                                 error=str(error).splitlines()[0][:300]) from error
    path = output_path(job, "", ".gif")
    save_gif(recorder, path, job["max_width"])
    return [{**describe_file(path, job), "frames": len(recorder.frames), "is_truncated": recorder.is_truncated}]


def run_job(job: dict) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "code": "browser_missing", "error": "Playwright is not installed"}
    if job.get("gif"):
        try:
            import PIL  # noqa: F401  (GIF 저장 전에 미리 확인)
        except ImportError:
            return {"ok": False, "code": "pillow_missing", "error": "Pillow is not installed"}
    Path(job["out_dir"]).mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(executable_path=find_browser_executable(playwright))
        except Exception as error:  # 브라우저 파일 없음, 실행 차단
            return {"ok": False, "code": "browser_missing", "error": str(error).splitlines()[0][:300]}
        try:
            return {"ok": True, "files": capture_gif(browser, job) if job.get("gif") else capture_png(browser, job)}
        except CaptureFailure as failure:
            return failure.payload
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    job = json.loads(Path(parser.parse_args().job).read_text(encoding="utf-8"))
    print(json.dumps(run_job(job), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
