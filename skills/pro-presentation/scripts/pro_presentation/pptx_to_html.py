"""One PPT slide > slide.html (pieces at their positions): text box > text, picture > image, shape > shape, table > table
Layout and fonts carried as inline styles. Moving them to theme.css variables when polishing is the agent's job (building.md)
"""
from __future__ import annotations

import html
from pathlib import Path

from pro_presentation.settings import SLIDE_WIDTH_PIXELS

PICTURE_SHAPE_TYPE = 13   # MSO_SHAPE_TYPE.PICTURE
GROUP_SHAPE_TYPE = 6      # MSO_SHAPE_TYPE.GROUP
# Paragraph alignment code > CSS (1 left, 2 center, 3 right, 4 justify)
ALIGNMENT_CSS = {1: "left", 2: "center", 3: "right", 4: "justify"}
ROUNDED_SHAPE_NAMES = ("ROUNDED_RECTANGLE",)
ELLIPSE_SHAPE_NAMES = ("OVAL",)


def _rgb(color) -> str | None:
    """python-pptx color > '#rrggbb' (None for non-RGB such as theme colors)"""
    try:
        return f"#{color.rgb}" if color is not None and color.type is not None and color.rgb is not None else None
    except (AttributeError, ValueError):
        return None


def _box_style(shape, pixels_per_emu: float) -> str:
    left, top = (shape.left or 0) * pixels_per_emu, (shape.top or 0) * pixels_per_emu
    width, height = (shape.width or 0) * pixels_per_emu, (shape.height or 0) * pixels_per_emu
    return f"left:{left:.0f}px;top:{top:.0f}px;width:{width:.0f}px;height:{height:.0f}px;"


def _text_html(shape, pixels_per_emu: float) -> str:
    """<p> per paragraph; runs in a line merge when size, weight and color match"""
    paragraphs = []
    for paragraph in shape.text_frame.paragraphs:
        runs = []
        for run in paragraph.runs:
            style = ""
            if run.font.size:
                style += f"font-size:{run.font.size * pixels_per_emu:.0f}px;"
            if run.font.bold:
                style += "font-weight:700;"
            color = _rgb(run.font.color) if run.font.color and run.font.color.type else None
            if color:
                style += f"color:{color};"
            text = html.escape(run.text)
            runs.append(f'<span style="{style}">{text}</span>' if style else text)
        alignment = ALIGNMENT_CSS.get(int(paragraph.alignment)) if paragraph.alignment else None
        paragraph_style = f' style="text-align:{alignment};"' if alignment else ""
        paragraphs.append(f"<p{paragraph_style}>{''.join(runs) or '&nbsp;'}</p>")
    return "".join(paragraphs)


def _fill_style(shape) -> str:
    style = ""
    try:
        if shape.fill.type == 1:   # MSO_FILL.SOLID
            color = _rgb(shape.fill.fore_color)
            if color:
                style += f"background:{color};"
    except (AttributeError, TypeError, ValueError):
        pass
    try:
        line_color = _rgb(shape.line.color) if shape.line.fill.type == 1 else None
        if line_color:
            style += f"border:2px solid {line_color};"
    except (AttributeError, TypeError, ValueError):
        pass
    try:
        name = shape.auto_shape_type.name if shape.shape_type == 1 else ""
    except (AttributeError, ValueError):
        name = ""
    if name in ROUNDED_SHAPE_NAMES:
        style += "border-radius:24px;"
    elif name in ELLIPSE_SHAPE_NAMES:
        style += "border-radius:50%;"
    return style


def _table_html(shape, pixels_per_emu: float) -> str:
    rows = []
    for row in shape.table.rows:
        cells = "".join(f"<td>{html.escape(cell.text)}</td>" for cell in row.cells)
        rows.append(f"<tr>{cells}</tr>")
    return (f'  <table data-pp="table" style="{_box_style(shape, pixels_per_emu)}border-collapse:collapse;">'
            f'{"".join(rows)}</table>')


def convert_slide(slide, slide_width_emu: int, folder: Path) -> tuple[str, int]:
    """One slide > (slide.html body, count of shapes not carried). Images saved to folder"""
    pixels_per_emu = SLIDE_WIDTH_PIXELS / slide_width_emu
    pieces, skipped, picture_count = [], 0, 0

    def add(shape) -> None:
        nonlocal skipped, picture_count
        box = _box_style(shape, pixels_per_emu)
        if shape.shape_type == GROUP_SHAPE_TYPE:
            for child in shape.shapes:   # group coordinate transform is approximate (child coordinates as is)
                add(child)
        elif shape.shape_type == PICTURE_SHAPE_TYPE:
            picture_count += 1
            file_name = f"picture-{picture_count}.{shape.image.ext}"
            (folder / file_name).write_bytes(shape.image.blob)
            pieces.append(f'  <img data-pp="image" src="{file_name}" alt="" style="{box}object-fit:contain;">')
        elif getattr(shape, "has_table", False) and shape.has_table:
            pieces.append(_table_html(shape, pixels_per_emu))
        elif shape.has_text_frame and shape.text_frame.text.strip():
            fill = _fill_style(shape)
            if fill:
                pieces.append(f'  <div data-pp="shape" style="{box}{fill}"></div>')
            is_title = shape.is_placeholder and "TITLE" in str(shape.placeholder_format.type)
            kind = "title" if is_title else "text"
            pieces.append(f'  <div data-pp="{kind}" style="{box}">{_text_html(shape, pixels_per_emu)}</div>')
        elif shape.shape_type == 1:   # shape without text
            fill = _fill_style(shape)
            if fill:
                pieces.append(f'  <div data-pp="shape" style="{box}{fill}"></div>')
        else:
            skipped += 1

    for shape in slide.shapes:
        add(shape)
    return '<section class="slide imported">\n' + "\n".join(pieces) + "\n</section>\n", skipped


def picture_slide_html(file_name: str) -> str:
    """Single-image slide (all-image PPT · PDF page)"""
    return ('<section class="slide imported">\n'
            f'  <img data-pp="image" src="{file_name}" alt="" '
            f'style="left:0;top:0;width:1920px;height:1080px;object-fit:contain;">\n</section>\n')
