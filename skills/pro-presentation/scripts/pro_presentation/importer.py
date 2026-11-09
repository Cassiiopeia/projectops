"""import: 기존 PPT·PDF > 장마다 slide.html (모든 장을 HTML 로) + 원본 글(notes.md) + deck.json 장 목록
PPT: 글 상자·도형·그림·표를 위치 그대로 조각으로 · 그림 한 장짜리 장은 그 그림을 담음 (다시 지을 장으로 표시)
PDF: 쪽 그림을 담음 (pdftoppm > PyMuPDF)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from common.emit import emit

from pro_presentation.deck import read_deck_settings
from pro_presentation.pptx_to_html import convert_slide, picture_slide_html
from pro_presentation.settings import (DECK_FILE_NAME, NOTES_FILE_NAME, SCRIPT_FILE_NAME, SLIDE_HTML_FILE_NAME,
                                       SLIDES_DIR_NAME)

TOOL_TIMEOUT_SECONDS = 300
PDF_RENDER_DPI = 110
PICTURE_SHAPE_TYPE = 13
REBUILD_NOTE = ("## Rebuild\nImported as one picture: the text is not editable yet. "
                "Rebuild it with pieces when it has to change (references/building.md).")


def load_python_pptx():
    """python-pptx > 없으면 사용자 영역 설치 1회 시도 > 그래도 없으면 None"""
    try:
        import pptx
        return pptx
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", "python-pptx"],
                       capture_output=True, encoding="utf-8", errors="replace", timeout=TOOL_TIMEOUT_SECONDS)
    try:
        import importlib
        import site
        importlib.invalidate_caches()
        sys.path.append(site.getusersitepackages())
        import pptx
        return pptx
    except ImportError:
        return None


def _slide_text(slide) -> str:
    parts = [shape.text_frame.text.strip() for shape in slide.shapes if shape.has_text_frame and shape.text_frame.text.strip()]
    if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
        parts.append("Speaker notes: " + slide.notes_slide.notes_text_frame.text.strip())
    return "\n".join(parts)


def _is_single_picture(slide) -> bool:
    pictures = [shape for shape in slide.shapes if shape.shape_type == PICTURE_SHAPE_TYPE]
    has_text = any(shape.has_text_frame and shape.text_frame.text.strip() for shape in slide.shapes)
    return len(pictures) == 1 and not has_text


def render_pdf(pdf_file: Path, work_dir: Path) -> list[Path] | None:
    """PDF > 쪽마다 jpg (pdftoppm > PyMuPDF). 도구가 없으면 None"""
    if shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-jpeg", "-r", str(PDF_RENDER_DPI), str(pdf_file), str(work_dir / "page")],
                       capture_output=True, encoding="utf-8", errors="replace", timeout=TOOL_TIMEOUT_SECONDS)
        pages = sorted(work_dir.glob("page*.jpg"))
        if pages:
            return pages
    try:
        import fitz
    except ImportError:
        return None
    pages = []
    with fitz.open(pdf_file) as document:
        for index, page in enumerate(document, start=1):
            target = work_dir / f"page-{index:03d}.jpg"
            page.get_pixmap(dpi=PDF_RENDER_DPI).save(target)
            pages.append(target)
    return pages


def _pdf_texts(pdf_file: Path) -> list[str]:
    if shutil.which("pdftotext") is None:
        return []
    result = subprocess.run(["pdftotext", "-layout", str(pdf_file), "-"], capture_output=True,
                            encoding="utf-8", errors="replace", timeout=TOOL_TIMEOUT_SECONDS)
    return [page.strip() for page in result.stdout.split("\f")]


class DeckWriter:
    """장 폴더 만들기 (deck.json 에 덧붙임, 같은 id 는 피함)"""

    def __init__(self, deck_dir: Path):
        self.deck_dir = deck_dir
        self.settings, _ = read_deck_settings(deck_dir)
        self.entries = self.settings.get("slides") or []
        self.existing = {entry if isinstance(entry, str) else entry.get("id") for entry in self.entries}
        self.created: list[str] = []
        self.rebuild: list[str] = []

    def new_folder(self, number: int) -> tuple[str, Path]:
        slide_id = f"{number:02d}"
        while slide_id in self.existing:
            slide_id += "-imported"
        folder = self.deck_dir / SLIDES_DIR_NAME / slide_id
        folder.mkdir(parents=True, exist_ok=True)
        self.existing.add(slide_id)
        return slide_id, folder

    def finish_slide(self, slide_id: str, folder: Path, slide_html: str, text: str, needs_rebuild: bool) -> None:
        (folder / SLIDE_HTML_FILE_NAME).write_text(slide_html, encoding="utf-8")
        notes = f"## Title\nSlide {len(self.created) + 1}\n\n## Original text\n{text}\n"
        if needs_rebuild:
            notes += f"\n{REBUILD_NOTE}\n"
            self.rebuild.append(slide_id)
        (folder / NOTES_FILE_NAME).write_text(notes, encoding="utf-8")
        (folder / SCRIPT_FILE_NAME).touch()
        self.entries.append({"id": slide_id, "kind": ""})
        self.created.append(slide_id)

    def save(self) -> None:
        self.settings["slides"] = self.entries
        (self.deck_dir / DECK_FILE_NAME).write_text(json.dumps(self.settings, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")


def import_pptx(source: Path, writer: DeckWriter) -> dict | None:
    pptx = load_python_pptx()
    if pptx is None:
        return {"ok": False, "code": "tool_missing", "error": "python-pptx is not installed and could not be installed",
                "next": "pip install --user python-pptx, or export the deck to PDF and import --pdf"}
    presentation = pptx.Presentation(str(source))
    skipped_total = 0
    for number, slide in enumerate(presentation.slides, start=1):
        slide_id, folder = writer.new_folder(number)
        if _is_single_picture(slide):
            picture = next(shape for shape in slide.shapes if shape.shape_type == PICTURE_SHAPE_TYPE)
            file_name = f"original.{picture.image.ext}"
            (folder / file_name).write_bytes(picture.image.blob)
            writer.finish_slide(slide_id, folder, picture_slide_html(file_name), _slide_text(slide), True)
        else:
            slide_html, skipped = convert_slide(slide, presentation.slide_width, folder)
            skipped_total += skipped
            writer.finish_slide(slide_id, folder, slide_html, _slide_text(slide), False)
    return {"skipped_shapes": skipped_total}


def import_pdf(source: Path, writer: DeckWriter, work_dir: Path) -> dict | None:
    pages = render_pdf(source, work_dir)
    if not pages:
        return {"ok": False, "code": "renderer_missing", "error": "No PDF renderer (pdftoppm or PyMuPDF)",
                "next": "brew install poppler, or pip install pymupdf"}
    texts = _pdf_texts(source)
    for number, page in enumerate(pages, start=1):
        slide_id, folder = writer.new_folder(number)
        shutil.copyfile(page, folder / "original.jpg")
        text = texts[number - 1] if number - 1 < len(texts) else ""
        writer.finish_slide(slide_id, folder, picture_slide_html("original.jpg"), text, True)
    return {}


def cmd_import(args) -> int:
    deck_dir = Path(args.deck).expanduser().resolve()
    if not (deck_dir / DECK_FILE_NAME).is_file():
        return emit({"ok": False, "code": "no_deck", "error": f"{deck_dir} has no deck.json",
                     "next": f"start --deck \"{deck_dir}\" first"})
    source = Path(args.pptx or args.pdf).expanduser()
    if not source.is_file():
        return emit({"ok": False, "code": "file_not_found", "error": f"{source} does not exist"})
    writer = DeckWriter(deck_dir)
    with tempfile.TemporaryDirectory() as temporary:
        result = import_pptx(source, writer) if args.pptx else import_pdf(source, writer, Path(temporary))
    if result and result.get("ok") is False:
        return emit(result)
    writer.save()
    return emit({"summary": f"Imported {len(writer.created)} slides from {source.name} as HTML "
                            f"({len(writer.rebuild)} are single pictures to rebuild when they change)",
                 "slide_ids": writer.created, "picture_slides": writer.rebuild,
                 "skipped_shapes": (result or {}).get("skipped_shapes", 0),
                 "next": ("Remove template slides the user does not need from deck.json, set each slide's kind and "
                          "title, write script.md from the user's material, then rehearse. Rebuild a picture slide "
                          "with pieces only when it has to change (references/building.md)")})
