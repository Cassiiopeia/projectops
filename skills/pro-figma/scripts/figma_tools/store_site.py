"""Build per-language landing page HTML · sitemap.xml · robots.txt strings (#1021)

Does not write files (commands/store_pages.py does). All external values are escaped.
No store badge images — they are trademark images, so only text links.
"""
from __future__ import annotations

import html
from xml.sax.saxutils import escape as xml_escape

X_DEFAULT = "x-default"


def page_url(base_url: str, folder: str | None) -> str:
    """Base URL + language folder (folder None for the root picker page)"""
    return base_url + (f"{folder}/" if folder else "")


def alternate_links(base_url: str, pages: list, default_folder: str) -> list[tuple[str, str]]:
    """(hreflang, URL) list: per language + x-default (default language page)"""
    links = [(page["hreflang"], page_url(base_url, page["folder"])) for page in pages]
    links.append((X_DEFAULT, page_url(base_url, default_folder)))
    return links


def _head_links(links: list[tuple[str, str]], canonical: str) -> str:
    alternates = "".join(f'<link rel="alternate" hreflang="{html.escape(code)}" href="{html.escape(url)}">'
                         for code, url in links)
    return f'<link rel="canonical" href="{html.escape(canonical)}">{alternates}'


def _font_css(theme: dict, font_prefix: str) -> tuple[str, str]:
    """(@font-face CSS, font-family stack). Font files are the site/fonts/ copies via relative paths"""
    faces = "".join(f"@font-face{{font-family:'{font['family']}';src:url('{font_prefix}{font['file_name']}');}}"
                    for font in theme["font_files"])
    stack = ",".join([f"'{font['family']}'" for font in theme["font_files"]] + [theme["font_family"]])
    return faces, stack


def _style(theme: dict, font_prefix: str) -> str:
    faces, stack = _font_css(theme, font_prefix)
    return (f"{faces}*{{box-sizing:border-box}}body{{margin:0;background:{theme['background']};"
            f"color:{theme['foreground']};font-family:{stack};line-height:1.5}}"
            "main{max-width:960px;margin:0 auto;padding:48px 16px}"
            "h1{font-size:clamp(28px,6vw,48px);line-height:1.15;margin:0 0 12px;word-break:keep-all}"
            ".sub{opacity:.85;font-size:18px;margin:0 0 28px}"
            f".stores a,.langs a{{display:inline-block;margin:0 12px 12px 0;padding:12px 18px;border-radius:10px;"
            f"background:{theme['accent']};color:{theme['background']};text-decoration:none;font-weight:700}}"
            ".features{padding-left:20px;margin:28px 0}.features li{margin-bottom:8px}"
            ".shots{display:flex;gap:16px;overflow-x:auto;padding-bottom:8px}"
            ".shots img{height:min(560px,70vh);width:auto;border-radius:16px;flex:none}"
            ".langs{margin-top:40px;font-size:14px}")


def _store_links(app: dict, labels: dict) -> str:
    links = []
    if app.get("app_store_url"):
        links.append(f'<a href="{html.escape(app["app_store_url"])}">{html.escape(labels["app_store"])}</a>')
    if app.get("play_url"):
        links.append(f'<a href="{html.escape(app["play_url"])}">{html.escape(labels["play"])}</a>')
    return f'<p class="stores">{"".join(links)}</p>' if links else ""


def _language_links(pages: list, base_url: str, current_folder: str | None) -> str:
    current_mark = ' aria-current="page"'
    links = "".join(f'<a href="{html.escape(page_url(base_url, page["folder"]))}" hreflang="{html.escape(page["hreflang"])}"'
                    f'{current_mark if page["folder"] == current_folder else ""}>'
                    f'{html.escape(page["language_name"])}</a>' for page in pages)
    return f'<nav class="langs">{links}</nav>'


def build_locale_page(page: dict, pages: list, site: dict) -> str:
    """One language page: title·description·store links·features·screenshots·language switch + hreflang"""
    canonical = page_url(site["base_url"], page["folder"])
    text = page["text"]
    features = "".join(f"<li>{html.escape(feature)}</li>" for feature in text.get("features", []))
    shots = "".join(f'<img src="images/{html.escape(name)}" alt="{html.escape(text["title"])} {index}" loading="lazy">'
                    for index, name in enumerate(page["image_names"], start=1))
    return (
        f'<!doctype html><html lang="{html.escape(page["hreflang"])}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html.escape(text["title"])}</title>'
        f'<meta name="description" content="{html.escape(text["description"])}">'
        f'<meta property="og:title" content="{html.escape(text["title"])}">'
        f'<meta property="og:description" content="{html.escape(text["description"])}">'
        f'<meta property="og:url" content="{html.escape(canonical)}">'
        f'{_head_links(site["links"], canonical)}<style>{_style(site["theme"], "../fonts/")}</style></head><body><main>'
        f'<h1>{html.escape(text.get("headline") or text["title"])}</h1>'
        f'<p class="sub">{html.escape(text.get("subtitle") or text["description"])}</p>'
        f'{_store_links(site["app"], page["store_labels"])}'
        f'{f"<ul class=features>{features}</ul>" if features else ""}'
        f'{f"<div class=shots>{shots}</div>" if shots else ""}'
        f'{_language_links(pages, site["base_url"], page["folder"])}</main></body></html>')


def build_root_page(pages: list, site: dict) -> str:
    """Root: language picker page (no auto redirect — crawlers follow the per-language pages as is)"""
    name = html.escape(site["app"].get("name") or "")
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{name}</title>{_head_links(site["links"], site["base_url"])}'
        f'<style>{_style(site["theme"], "fonts/")}</style></head><body><main><h1>{name}</h1>'
        f'{_language_links(pages, site["base_url"], None)}</main></body></html>')


def build_sitemap(site: dict, pages: list) -> str:
    """<url> per language URL + xhtml:link for every language (including x-default)"""
    alternates = "".join(f'<xhtml:link rel="alternate" hreflang="{xml_escape(code)}" href="{xml_escape(url)}"/>'
                         for code, url in site["links"])
    urls = "".join(f"<url><loc>{xml_escape(page_url(site['base_url'], page['folder']))}</loc>{alternates}</url>"
                   for page in pages)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{urls}</urlset>\n')


def build_robots(base_url: str) -> str:
    return f"User-agent: *\nAllow: /\nSitemap: {base_url}sitemap.xml\n"
