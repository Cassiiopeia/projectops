"""스토어 이미지 1장의 HTML 생성 (#1021)

기기 틀은 CSS 로 그린 중립 사각형 — 서드파티 기기 이미지를 쓰지 않는다.
크기 기준값은 캔버스 너비(W)·높이(H) 비율로 계산해 어느 슬롯 크기에서도 같은 모양이 나온다.
"""
from __future__ import annotations

import html
from pathlib import Path

from figma_tools.store_scenes import BANNER_LAYOUT

# 글자 넘침 검사 대상 표시 (렌더 스크립트가 이 속성을 찾는다)
FIT_ATTRIBUTE = "data-fit"
DEVICE_FRAME_COLOR = "#101418"


def _text_html(text: str) -> str:
    """이스케이프 후 줄바꿈만 <br> 로 (제목에 \\n 허용)"""
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
    """문구 + 기기 틀(앱 캡처). caption-top 은 문구가 위, caption-bottom 은 아래"""
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
    """문구만(+ 선택 아이콘) 있는 가로 배너 (Play 그래픽 이미지 등)"""
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
