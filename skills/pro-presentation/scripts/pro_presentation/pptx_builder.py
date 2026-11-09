"""PPT 조립기: layout.json > 글자를 고칠 수 있는 PPT (글 상자 · 도형 · 그림 · 표, 대본은 발표자 노트)
python-pptx 가 있는 파이썬으로 단독 실행. 결과 JSON 한 줄 (장마다 PPT 에 들어간 글)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Pt

SLIDE_WIDTH_PIXELS = 1920
SLIDE_WIDTH_EMU = 12192000    # 13.333 in (16:9)
SLIDE_HEIGHT_EMU = 6858000    # 7.5 in
EMU_PER_PIXEL = SLIDE_WIDTH_EMU / SLIDE_WIDTH_PIXELS
POINTS_PER_PIXEL = EMU_PER_PIXEL / 12700
BOLD_WEIGHT = 600
RGB_PATTERN = re.compile(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)")
ALIGNMENTS = {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT, "end": PP_ALIGN.RIGHT, "justify": PP_ALIGN.JUSTIFY}
BLANK_LAYOUT_INDEX = 6


def parse_color(value: str | None) -> RGBColor | None:
    """'rgb(1, 2, 3)' > 색 (투명은 None)"""
    match = RGB_PATTERN.match(value or "")
    if not match or (match.group(4) is not None and float(match.group(4)) == 0):
        return None
    return RGBColor(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def emu_box(box: list[float]) -> tuple[Emu, Emu, Emu, Emu]:
    return tuple(Emu(int(max(0.0, value) * EMU_PER_PIXEL)) for value in box)


def first_font(font_family: str) -> str:
    return (font_family or "").split(",")[0].strip().strip('"').strip("'")


def add_text(slide, piece: dict) -> None:
    textbox = slide.shapes.add_textbox(*emu_box(piece["box"]))
    frame = textbox.text_frame
    frame.word_wrap = True
    top, right, bottom, left = piece.get("padding") or [0, 0, 0, 0]
    frame.margin_top, frame.margin_right = Emu(int(top * EMU_PER_PIXEL)), Emu(int(right * EMU_PER_PIXEL))
    frame.margin_bottom, frame.margin_left = Emu(int(bottom * EMU_PER_PIXEL)), Emu(int(left * EMU_PER_PIXEL))
    lines = [line for line in piece.get("lines") or [""]]
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = ALIGNMENTS.get(piece.get("align"), PP_ALIGN.LEFT)
        run = paragraph.add_run()
        run.text = ("• " + line) if piece.get("is_list") and line.strip() else line
        run.font.size = Pt(round(piece["font_size"] * POINTS_PER_PIXEL, 1))
        run.font.bold = (piece.get("font_weight") or 400) >= BOLD_WEIGHT
        run.font.name = first_font(piece.get("font_family"))
        color = parse_color(piece.get("color"))
        if color:
            run.font.color.rgb = color
    background = parse_color(piece.get("background"))
    if background:
        textbox.fill.solid()
        textbox.fill.fore_color.rgb = background


def add_shape(slide, piece: dict) -> None:
    left, top, width, height = piece["box"]
    radius = piece.get("radius") or "0px"
    radius_pixels = float(radius.rstrip("px%") or 0)
    if radius.endswith("%") or radius_pixels >= min(width, height) / 2 - 1:
        kind = MSO_SHAPE.OVAL if radius_pixels > 0 else MSO_SHAPE.RECTANGLE
    else:
        kind = MSO_SHAPE.ROUNDED_RECTANGLE if radius_pixels > 0 else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(kind, *emu_box(piece["box"]))
    if kind == MSO_SHAPE.ROUNDED_RECTANGLE and min(width, height) > 0:
        shape.adjustments[0] = min(0.5, radius_pixels / min(width, height))
    fill = parse_color(piece.get("background"))
    if fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    else:
        shape.fill.background()
    border = parse_color(piece.get("border_color")) if piece.get("border_width") else None
    if border:
        shape.line.color.rgb = border
        shape.line.width = Emu(int(piece["border_width"] * EMU_PER_PIXEL))
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False


def resolve_image(src: str, deck_dir: Path) -> Path | None:
    """렌더 주소(/deck/...) > 덱 안 파일"""
    path = urllib.parse.unquote(urllib.parse.urlsplit(src).path)
    if "/deck/" not in path:
        return None
    candidate = (deck_dir / path.split("/deck/", 1)[1]).resolve()
    return candidate if candidate.is_file() and deck_dir.resolve() in candidate.parents else None


def add_table(slide, piece: dict) -> None:
    rows = piece.get("rows") or [[""]]
    columns = max(len(row) for row in rows)
    table = slide.shapes.add_table(len(rows), columns, *emu_box(piece["box"])).table
    for row_index, row in enumerate(rows):
        for column_index in range(columns):
            cell = table.cell(row_index, column_index)
            cell.text = row[column_index] if column_index < len(row) else ""
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(round(piece["font_size"] * POINTS_PER_PIXEL, 1))
                    run.font.name = first_font(piece.get("font_family"))


def build(layout: dict, deck_dir: Path, out_dir: Path, scripts: dict, output: Path) -> dict:
    presentation = Presentation()
    presentation.slide_width, presentation.slide_height = Emu(SLIDE_WIDTH_EMU), Emu(SLIDE_HEIGHT_EMU)
    report = []
    for slide_layout in layout["slides"]:
        slide = presentation.slides.add_slide(presentation.slide_layouts[BLANK_LAYOUT_INDEX])
        missing_images = []
        # 조각 아닌 부분(배경 등) 먼저 그림으로 > 조각을 문서 순서대로
        for picture in slide_layout["pictures"]:
            slide.shapes.add_picture(str(out_dir / picture["file"]), *emu_box(picture["box"]))
        for piece in slide_layout["pieces"]:
            if piece["kind"] in ("text", "title"):
                add_text(slide, piece)
            elif piece["kind"] == "shape":
                add_shape(slide, piece)
            elif piece["kind"] == "table":
                add_table(slide, piece)
            elif piece["kind"] == "image":
                image = resolve_image(piece.get("src", ""), deck_dir)
                if image is None:
                    missing_images.append(piece.get("src", ""))
                else:
                    slide.shapes.add_picture(str(image), *emu_box(piece["box"]))
        script = scripts.get(slide_layout["id"], "")
        if script:
            slide.notes_slide.notes_text_frame.text = script
        texts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]
        texts += [cell.text for shape in slide.shapes if shape.has_table for row in shape.table.rows for cell in row.cells]
        report.append({"id": slide_layout["id"], "texts": texts, "missing_images": missing_images})
    presentation.save(str(output))
    return {"ok": True, "pptx": str(output), "slides": report}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    job = json.loads(Path(parser.parse_args().job).read_text(encoding="utf-8"))
    out_dir = Path(job["out_dir"])
    layout = json.loads((out_dir / "layout.json").read_text(encoding="utf-8"))
    result = build(layout, Path(job["deck_dir"]), out_dir, job.get("scripts") or {}, Path(job["pptx"]))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
