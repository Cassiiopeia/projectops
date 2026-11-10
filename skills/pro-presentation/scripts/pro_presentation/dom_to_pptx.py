"""dom-to-pptx 변환기 (MIT): 번들 준비(처음 쓸 때 받음, 버전 · 해시 고정) > 브라우저 안에서 장 DOM > 고칠 수 있는 PPT
단독 실행 (Playwright 가 있는 파이썬): 작업 JSON > 결과 JSON 한 줄 (pptx_builder.py 와 같은 모양)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

CONVERTER_NAME = "dom-to-pptx"
# 출처: https://github.com/atharva9167j/dom-to-pptx (저장소에 넣지 않고 ~/.projectops/presentation/vendor/ 에 받아 둠, 3.7MB)
BUNDLE_VERSION = "2.1.2"
BUNDLE_FILE_NAME = f"dom-to-pptx-{BUNDLE_VERSION}.bundle.js"
# npm 배포본 dist/dom-to-pptx.bundle.js 의 SHA-256 (버전을 올리면 함께 바꿈)
BUNDLE_SHA256 = "df8fca27232864a4ad01d7ad8a5be1e867ab26b9562a3e5e66c8429b644256d4"
BUNDLE_URLS = (f"https://cdn.jsdelivr.net/npm/dom-to-pptx@{BUNDLE_VERSION}/dist/dom-to-pptx.bundle.js",
               f"https://unpkg.com/dom-to-pptx@{BUNDLE_VERSION}/dist/dom-to-pptx.bundle.js")
BUNDLE_DOWNLOAD_TIMEOUT_SECONDS = 60
# 번들 최대 크기 (16MB): 엉뚱한 응답을 끝없이 받지 않게
BUNDLE_MAX_BYTES = 16 * 1024 * 1024
SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080
SLIDE_FILE_PATTERN = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
PARAGRAPH_PATTERN = re.compile(r"<a:p>.*?</a:p>|<a:p/>", re.S)
TEXT_RUN_PATTERN = re.compile(r"<a:t>(.*?)</a:t>", re.S)

# 장마다 독립 iframe (/render/<id>) 에 그림: 장끼리 스타일이 섞이지 않고 그림 주소도 그대로. 대본은 발표자 노트로
LOAD_SLIDES_SCRIPT = """
async ([slideIds, scripts]) => {
  document.documentElement.innerHTML = "<head></head><body style='margin:0'></body>";
  const sections = [];
  for (const slideId of slideIds) {
    const frame = document.createElement("iframe");
    frame.style.cssText = "width:1920px;height:1080px;border:0;display:block";
    frame.src = "/render/" + encodeURIComponent(slideId);
    document.body.append(frame);
    await new Promise((resolve) => frame.addEventListener("load", resolve, { once: true }));
    const section = frame.contentDocument.querySelector("section.slide");
    if (!section) continue;
    await Promise.all([...frame.contentDocument.images].map((image) => image.decode().catch(() => null)));
    if (scripts[slideId]) {
      const note = frame.contentDocument.createElement("template");
      note.setAttribute("data-pptx-notes", "");
      note.content.append(scripts[slideId]);
      section.append(note);
    }
    sections.push(section);
  }
  window.slideSections = sections;
  return sections.length;
}
"""
# 변환 > PPT 바이트를 base64 로 (파일 저장은 파이썬 쪽)
CONVERT_SCRIPT = """
async () => {
  const blob = await domToPptx.exportToPptx(window.slideSections, { skipDownload: true, fileName: "deck.pptx" });
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  return btoa(binary);
}
"""


def is_expected_bundle(path: Path) -> bool:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() == BUNDLE_SHA256
    except OSError:
        return False


def ensure_bundle(vendor_dir: Path) -> tuple[Path | None, str]:
    """(번들 경로, 사유). 받아 둔 것이 있으면 그것, 없으면 내려받아 해시 확인 (다르면 버림)"""
    target = vendor_dir / BUNDLE_FILE_NAME
    if is_expected_bundle(target):
        return target, "cached"
    reason = "download_failed"
    for url in BUNDLE_URLS:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "projectops"})
            with urllib.request.urlopen(request, timeout=BUNDLE_DOWNLOAD_TIMEOUT_SECONDS) as response:
                body = response.read(BUNDLE_MAX_BYTES + 1)
        except (OSError, urllib.error.URLError, ValueError):
            continue
        if hashlib.sha256(body).hexdigest() != BUNDLE_SHA256:
            reason = "hash_mismatch"
            continue
        vendor_dir.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        partial.write_bytes(body)
        os.replace(partial, target)
        return target, "downloaded"
    return None, reason


def read_slide_texts(pptx_file: Path) -> list[list[str]]:
    """PPT 장마다 문단 글 (검수용, 표준 라이브러리만). 한 문단 안에서 나뉜 글씨는 이어 붙임"""
    with zipfile.ZipFile(pptx_file) as archive:
        numbered = sorted((int(match.group(1)), name) for name in archive.namelist()
                          if (match := SLIDE_FILE_PATTERN.match(name)))
        slides = []
        for _, name in numbered:
            xml = archive.read(name).decode("utf-8", errors="replace")
            paragraphs = ("".join(TEXT_RUN_PATTERN.findall(paragraph)) for paragraph in PARAGRAPH_PATTERN.findall(xml))
            slides.append([html.unescape(text) for text in paragraphs if text])
    return slides


def convert(job: dict) -> dict:
    """작업 > PPT 파일. 장 수가 맞지 않으면 실패 (호출부가 내장 변환기로 대신함)"""
    from export_worker import find_browser_executable   # 같은 폴더 (단독 실행)
    from playwright.sync_api import sync_playwright
    slide_ids = [slide["id"] for slide in job["slides"]]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=find_browser_executable(playwright))
        context = browser.new_context(viewport={"width": SLIDE_WIDTH, "height": SLIDE_HEIGHT},
                                      extra_http_headers={"X-Presentation-Key": job["key"]})
        page = context.new_page()
        page.goto(f"{job['base_url']}/render/{slide_ids[0]}", wait_until="networkidle")
        loaded = page.evaluate(LOAD_SLIDES_SCRIPT, [slide_ids, job.get("scripts") or {}])
        if loaded != len(slide_ids):
            browser.close()
            return {"ok": False, "code": "slide_count_mismatch", "error": f"Loaded {loaded} of {len(slide_ids)} slides"}
        page.add_script_tag(path=job["bundle"])
        Path(job["pptx"]).write_bytes(base64.b64decode(page.evaluate(CONVERT_SCRIPT)))
        browser.close()
    texts = read_slide_texts(Path(job["pptx"]))
    if len(texts) != len(slide_ids):
        return {"ok": False, "code": "slide_count_mismatch", "error": f"The PPT has {len(texts)} of {len(slide_ids)} slides"}
    return {"ok": True, "pptx": job["pptx"], "converter": CONVERTER_NAME,
            "slides": [{"id": slide_id, "texts": slide_texts, "missing_images": []}
                       for slide_id, slide_texts in zip(slide_ids, texts)]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    job = json.loads(Path(parser.parse_args().job).read_text(encoding="utf-8"))
    try:
        result = convert(job)
    except ImportError:
        result = {"ok": False, "code": "browser_missing", "error": "Playwright is not installed"}
    except Exception as error:  # 변환 실패는 결과로 돌려줌 (호출부가 내장 변환기로 대신함)
        result = {"ok": False, "code": "convert_failed", "error": str(error)[:400]}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
