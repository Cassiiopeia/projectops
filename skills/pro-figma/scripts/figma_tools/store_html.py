"""HTML for one store image (#1021)

The device frame is a neutral CSS-drawn rectangle — no third-party device images.
Sizes derive from canvas width (W)·height (H) ratios, so the shape is the same at any slot size.
"""
from __future__ import annotations

import html
from pathlib import Path

from figma_tools.store_scenes import BANNER_LAYOUT

# Marks text-overflow check targets (the render script looks for this attribute)
FIT_ATTRIBUTE = "data-fit"
DEVICE_FRAME_COLOR = "#101418"


def _text_html(text: str) -> str:
    """Escape, then only line breaks become <br> (\\n allowed in titles)"""
    return html.escape(text).replace("\n", "<br>")


def _font_face_css(theme: dict) -> str:
    return "".join(
        f"@font-face{{font-family:'{font['family']}';src:url('{Path(font['path']).resolve().as_uri()}');}}"
        for font in theme["font_files"])


def _font_stack(theme: dict) -> str:
    families = [f"'{font['family']}'" for font in theme["font_files"]]
    return ",".join(families + [theme["font_family"]])


def build_html(job: dict, theme: dict) -> str:
    width, height = job["width"], job["height"]
    if job["layout"] == BANNER_LAYOUT:
        body_css, body_html = _banner_parts(job, theme)
    else:
        body_css, body_html = _caption_parts(job, theme)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><style>"
        f"{_font_face_css(theme)}"
        "html,body{margin:0;padding:0}"
        f"body{{width:{width}px;height:{height}px;overflow:hidden;position:relative;"
        f"background:{theme['background']};color:{theme['foreground']};"
        f"font-family:{_font_stack(theme)};-webkit-font-smoothing:antialiased}}"
        f".title{{font-weight:800;line-height:1.18;word-break:keep-all;overflow-wrap:anywhere}}"
        f".subtitle{{opacity:.82;line-height:1.3;word-break:keep-all;overflow-wrap:anywhere}}"
        f"{body_css}</style></head><body>{body_html}</body></html>")


def _caption_parts(job: dict, theme: dict) -> tuple[str, str]:
    """Caption + device frame (app capture). caption-top puts the caption above, caption-bottom below"""
    width, height = job["width"], job["height"]
    side_pad = round(width * 0.07)
    margin = round(height * 0.05)
    caption_height = round(height * 0.17)
    gap = round(width * 0.04)
    border = round(width * 0.016)
    is_caption_top = job["layout"] == "caption-top"
    caption_top = margin if is_caption_top else height - margin - caption_height
    device_top = margin + caption_height + gap if is_caption_top else margin
    device_height = (height - device_top + border * 2) if is_caption_top \
        else caption_top - gap - device_top
    radius = round(width * 0.07)
    device_radius = f"{radius}px" if is_caption_top else f"{radius}px {radius}px 0 0"
    subtitle_px = round(width * 0.036)
    css = (
        f".caption{{position:absolute;left:{side_pad}px;right:{side_pad}px;top:{caption_top}px;"
        f"height:{caption_height}px;overflow:hidden;text-align:center;display:flex;flex-direction:column;justify-content:center}}"
        f".title{{font-size:{round(width * 0.074)}px}}"
        f".subtitle{{font-size:{subtitle_px}px;margin-top:{round(width * 0.02)}px}}"
        f".device{{position:absolute;left:50%;transform:translateX(-50%);top:{device_top}px;"
        f"width:{round(width * 0.78)}px;height:{device_height}px;box-sizing:border-box;"
        f"border:{border}px solid {DEVICE_FRAME_COLOR};background:#000;overflow:hidden;"
        f"border-radius:{device_radius};box-shadow:0 {round(width * 0.02)}px {round(width * 0.06)}px rgba(0,0,0,.35)}}"
        ".device img{display:block;width:100%}")
    subtitle = f"<div class=\"subtitle\">{_text_html(job['subtitle'])}</div>" if job["subtitle"] else ""
    body = (f"<div class=\"caption\" {FIT_ATTRIBUTE}><div class=\"title\">{_text_html(job['title'])}</div>"
            f"{subtitle}</div>"
            f"<div class=\"device\"><img src=\"{Path(job['screenshot']).resolve().as_uri()}\" alt=\"\"></div>")
    return css, body


def _banner_parts(job: dict, theme: dict) -> tuple[str, str]:
    """Horizontal banner with caption only (+ optional icon) (Play feature graphic etc.)"""
    width, height = job["width"], job["height"]
    pad = round(height * 0.12)
    icon_size = round(height * 0.52)
    has_icon = bool(job["icon"])
    text_width = width - pad * 2 - (icon_size + pad if has_icon else 0)
    css = (
        f".banner-text{{position:absolute;left:{pad}px;top:{pad}px;width:{text_width}px;"
        f"height:{height - pad * 2}px;overflow:hidden;display:flex;flex-direction:column;justify-content:center}}"
        f".title{{font-size:{round(height * 0.15)}px}}"
        f".subtitle{{font-size:{round(height * 0.072)}px;margin-top:{round(height * 0.04)}px}}"
        f".accent-bar{{width:{round(height * 0.2)}px;height:{max(4, round(height * 0.014))}px;"
        f"background:{theme['accent']};margin-bottom:{round(height * 0.05)}px}}"
        f".icon{{position:absolute;right:{pad}px;top:{round((height - icon_size) / 2)}px;"
        f"width:{icon_size}px;height:{icon_size}px;border-radius:{round(icon_size * 0.22)}px}}")
    subtitle = f"<div class=\"subtitle\">{_text_html(job['subtitle'])}</div>" if job["subtitle"] else ""
    icon = f"<img class=\"icon\" src=\"{Path(job['icon']).resolve().as_uri()}\" alt=\"\">" if has_icon else ""
    body = (f"<div class=\"banner-text\" {FIT_ATTRIBUTE}><div class=\"accent-bar\"></div>"
            f"<div class=\"title\">{_text_html(job['title'])}</div>{subtitle}</div>{icon}")
    return css, body
