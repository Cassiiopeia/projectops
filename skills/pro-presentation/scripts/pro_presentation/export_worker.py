"""Export runner: job JSON > per slide PNG + piece values (layout.json) + image of non-piece parts + PDF
Runs with the pro-launch venv Python (Playwright and Pillow may be missing from system Python). Result is one JSON line
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080
RENDER_WAIT_MILLISECONDS = 600
# skills/pro-launch/scripts/browser_pick.py (this file: skills/pro-presentation/scripts/pro_presentation/)
BROWSER_PICK_FILE = Path(__file__).resolve().parents[3] / "pro-launch" / "scripts" / "browser_pick.py"

# Read piece values in a slide: data-pp pieces · non-piece top-level elements (parts that become images) · shapes the built-in converter cannot carry (unmapped)
COLLECT_PIECES_SCRIPT = """
() => {
  const slide = document.querySelector("section.slide");
  if (!slide) return { pieces: [], pictures: [], unmapped: [] };
  const origin = slide.getBoundingClientRect();
  const box = (element) => { const r = element.getBoundingClientRect(); return [r.left - origin.left, r.top - origin.top, r.width, r.height]; };
  const pieces = [...slide.querySelectorAll("[data-pp]")].map((element, index) => {
    const style = getComputedStyle(element);
    const piece = { index, kind: element.dataset.pp, box: box(element), font_family: style.fontFamily,
      font_size: parseFloat(style.fontSize), font_weight: parseInt(style.fontWeight, 10), color: style.color,
      align: style.textAlign, line_height: parseFloat(style.lineHeight) || null, background: style.backgroundColor,
      border_color: style.borderTopColor, border_width: parseFloat(style.borderTopWidth) || 0,
      radius: style.borderTopLeftRadius, padding: [parseFloat(style.paddingTop), parseFloat(style.paddingRight), parseFloat(style.paddingBottom), parseFloat(style.paddingLeft)] };
    if (piece.kind === "image") piece.src = element.currentSrc || element.src || "";
    else if (piece.kind === "table") piece.rows = [...element.rows].map((row) => [...row.cells].map((cell) => cell.innerText.trim()));
    else piece.lines = element.innerText.split("\\n").map((line) => line.trimEnd());
    piece.is_list = ["UL", "OL"].includes(element.tagName);
    return piece;
  });
  const pictures = [...slide.children].filter((element) => !element.dataset.pp && !["STYLE", "SCRIPT"].includes(element.tagName))
    .map((element, index) => { element.dataset.ppPicture = String(index); return { index, box: box(element) }; });
  const unmapped = new Set(pictures.length ? ["parts without data-pp"] : []);
  for (const element of slide.querySelectorAll("[data-pp]")) {
    const style = getComputedStyle(element);
    const kind = element.dataset.pp;
    if (style.backgroundImage !== "none") unmapped.add("gradient or image background");
    if (style.boxShadow !== "none") unmapped.add("shadow");
    if (/rgba\\(.*,\\s*0?\\.\\d+\\)/.test(style.backgroundColor)) unmapped.add("see-through fill");
    if (["dashed", "dotted"].includes(style.borderTopStyle) && parseFloat(style.borderTopWidth) > 0) unmapped.add("dashed border");
    if (kind === "table") unmapped.add("table style");
    if (kind === "image" && parseFloat(style.borderTopLeftRadius) > 0) unmapped.add("rounded picture");
    if (element.tagName === "OL") unmapped.add("numbered list");
    if (kind === "text" || kind === "title") {
      const hasMixedStyle = [...element.querySelectorAll("*")].some((child) => {
        const inner = getComputedStyle(child);
        return inner.color !== style.color || inner.fontWeight !== style.fontWeight || inner.fontStyle !== style.fontStyle;
      });
      if (hasMixedStyle) unmapped.add("mixed text styles");
    }
  }
  return { pieces, pictures, unmapped: [...unmapped] };
}
"""


def find_browser_executable(playwright) -> str | None:
    """Same browser as the pro-launch rule (env var > bundled Chromium > installed Chrome, Edge)"""
    spec = importlib.util.spec_from_file_location("browser_pick", BROWSER_PICK_FILE)
    if spec is None or not BROWSER_PICK_FILE.is_file():
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        bundled = playwright.chromium.executable_path
    except Exception:  # treat like no bundle
        bundled = None
    return module.resolve(bundled).get("exe")


def capture_slide(page, job: dict, slide: dict, out_dir: Path) -> dict:
    """One slide: render > PNG > piece values > image of non-piece parts (pieces inside hidden)"""
    page.goto(f"{job['base_url']}/render/{slide['id']}", wait_until="networkidle")
    page.wait_for_timeout(RENDER_WAIT_MILLISECONDS)
    png = out_dir / f"slide-{slide['number']:02d}.png"
    page.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": SLIDE_WIDTH, "height": SLIDE_HEIGHT})
    layout = page.evaluate(COLLECT_PIECES_SCRIPT)
    for picture in layout["pictures"]:
        element = page.locator(f'[data-pp-picture="{picture["index"]}"]')
        element.evaluate("element => element.querySelectorAll('[data-pp]').forEach(child => child.style.visibility = 'hidden')")
        picture_file = out_dir / f"slide-{slide['number']:02d}-picture-{picture['index']}.png"
        element.screenshot(path=str(picture_file), omit_background=True)
        element.evaluate("element => element.querySelectorAll('[data-pp]').forEach(child => child.style.visibility = '')")
        picture["file"] = picture_file.name
    return {"id": slide["id"], "number": slide["number"], "png": png.name, **layout}


def write_pdf(png_files: list[Path], pdf_file: Path) -> None:
    from PIL import Image
    pages = [Image.open(path).convert("RGB") for path in png_files]
    pages[0].save(pdf_file, save_all=True, append_images=pages[1:], resolution=144)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    job = json.loads(Path(parser.parse_args().job).read_text(encoding="utf-8"))
    out_dir = Path(job["out_dir"])
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"ok": False, "code": "browser_missing", "error": "Playwright is not installed"}))
        return 1
    slides = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=find_browser_executable(playwright))
        context = browser.new_context(viewport={"width": SLIDE_WIDTH, "height": SLIDE_HEIGHT},
                                      extra_http_headers={"X-Presentation-Key": job["key"]})
        page = context.new_page()
        for slide in job["slides"]:
            slides.append(capture_slide(page, job, slide, out_dir))
        browser.close()
    (out_dir / "layout.json").write_text(json.dumps({"slides": slides}, ensure_ascii=False, indent=1), encoding="utf-8")
    if job.get("pdf"):
        write_pdf([out_dir / slide["png"] for slide in slides], Path(job["pdf"]))
    print(json.dumps({"ok": True, "slides": len(slides), "layout": str(out_dir / "layout.json")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
