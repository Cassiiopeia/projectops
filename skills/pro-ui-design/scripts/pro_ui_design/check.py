"""시안 검사 4개: 토큰 밖 색, 로드 안 된 글꼴, 외부 URL, 깨진 경로 (사실만 보고, 판단은 에이전트)"""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from common.emit import emit

from pro_ui_design.session import find_session

TOKENS_FILE_NAME = "tokens.css"
HEX_COLOR_PATTERN = re.compile(r"(?<![&\w])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b(?!\s*[{.:>+~\[,]\s*[^\s;}]*\s*\{)(?!\s*\{)")
ANCHOR_PATTERN = re.compile(r"""(href|xlink:href)\s*=\s*["']#[^"']*["']|url\(\s*["']?#[^)]*\)""", re.IGNORECASE)
HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
FONT_FAMILY_PATTERN = re.compile(r"font-family\s*:\s*([^;}\"<]*(?:\"[^\"]*\"[^;}\"<]*)*)", re.IGNORECASE)
FONT_SHORTHAND_FACE_PATTERN = re.compile(r"@font-face\s*\{[^}]*?font-family\s*:\s*[\"']?([^\"';}]+)", re.IGNORECASE)
RESOURCE_PATTERNS = (
    re.compile(r"""\b(?:src|poster)\s*=\s*["']([^"']+)["']""", re.IGNORECASE),
    re.compile(r"""<link\b[^>]*\bhref\s*=\s*["']([^"']+)["']""", re.IGNORECASE),
    re.compile(r"""url\(\s*["']?([^"')]+)["']?\s*\)""", re.IGNORECASE),
    re.compile(r"""@import\s+["']([^"']+)["']""", re.IGNORECASE),
)
# 어느 PC 에나 있거나 OS 가 알아서 고르는 글꼴: 미로드로 치지 않음
SYSTEM_FONTS = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif", "ui-serif",
                "ui-monospace", "ui-rounded", "-apple-system", "blinkmacsystemfont", "segoe ui", "helvetica",
                "helvetica neue", "arial", "times", "times new roman", "courier", "courier new", "menlo", "monaco",
                "consolas", "apple sd gothic neo", "malgun gothic", "inherit", "initial", "unset", "emoji",
                "apple color emoji", "segoe ui emoji", "noto color emoji"}
SKIPPED_PATH_PREFIXES = ("data:", "blob:", "#", "about:", "/assets/", "${", "{{", "mailto:", "tel:")
FILES_ROUTE_PREFIX = "/files/"


def _normalize_hex(value: str) -> str:
    lowered = value.lower()
    if len(lowered) in (3, 4):
        lowered = "".join(character * 2 for character in lowered)
    return "#" + lowered


def _find_colors(text: str) -> set[str]:
    cleaned = ANCHOR_PATTERN.sub(" ", HTML_COMMENT_PATTERN.sub(" ", text))
    return {_normalize_hex(match) for match in HEX_COLOR_PATTERN.findall(cleaned)}


def _find_font_faces(text: str) -> set[str]:
    return {name.strip().lower() for name in FONT_SHORTHAND_FACE_PATTERN.findall(text)}


def _find_font_families(text: str) -> set[str]:
    without_faces = re.sub(r"@font-face\s*\{[^}]*\}", " ", text, flags=re.IGNORECASE)
    families = set()
    for declaration in FONT_FAMILY_PATTERN.findall(without_faces):
        for name in declaration.split(","):
            cleaned = name.strip().strip("\"'").strip()
            if cleaned and not cleaned.lower().startswith("var("):
                families.add(cleaned)
    return families


def _find_resources(text: str) -> set[str]:
    cleaned = HTML_COMMENT_PATTERN.sub(" ", text)
    return {match.strip() for pattern in RESOURCE_PATTERNS for match in pattern.findall(cleaned)}


def _is_missing_local_path(reference: str, screens_dir: Path) -> bool:
    relative = reference.split("?")[0].split("#")[0]
    if relative.startswith(FILES_ROUTE_PREFIX):
        relative = relative[len(FILES_ROUTE_PREFIX):]
    if not relative or relative.startswith("/"):
        return bool(relative)
    return not (screens_dir / urllib.parse.unquote(relative)).exists()


def check_screens(screens_dir: Path, screen_files: list[Path]) -> dict:
    tokens_file = screens_dir / TOKENS_FILE_NAME
    tokens_text = tokens_file.read_text(encoding="utf-8", errors="replace") if tokens_file.is_file() else ""
    known_colors = _find_colors(tokens_text)
    unknown_colors, unloaded_fonts, external_urls, broken_paths = set(), set(), set(), set()
    for screen_file in screen_files:
        text = screen_file.read_text(encoding="utf-8", errors="replace")
        unknown_colors |= _find_colors(text) - known_colors
        loaded_fonts = _find_font_faces(tokens_text) | _find_font_faces(text)
        unloaded_fonts |= {name for name in _find_font_families(text)
                           if name.lower() not in loaded_fonts and name.lower() not in SYSTEM_FONTS}
        for reference in _find_resources(text) | _find_resources(tokens_text):
            if reference.startswith(("http://", "https://", "//")):
                external_urls.add(reference)
            elif not reference.startswith(SKIPPED_PATH_PREFIXES) and _is_missing_local_path(reference, screens_dir):
                broken_paths.add(reference)
    return {"unknown_colors": sorted(unknown_colors), "unloaded_fonts": sorted(unloaded_fonts),
            "external_urls": sorted(external_urls), "broken_paths": sorted(broken_paths),
            "has_tokens_css": tokens_file.is_file()}


def cmd_check(args) -> int:
    session = find_session(Path(args.root).resolve(), args.title)
    if session is None:
        return emit({"ok": False, "code": "no_session", "error": "No mockup session for this project",
                     "next": "ui_design_cli.py start --title <screen name>"})
    screens_dir = session.screens_dir
    if args.screen:
        screen_files = [screens_dir / args.screen]
        if not screen_files[0].is_file():
            return emit({"ok": False, "code": "screen_not_found", "error": f"No mockup named {args.screen}"})
    else:
        screen_files = sorted(path for path in screens_dir.glob("*.html") if not path.name.startswith("_"))
    result = check_screens(screens_dir, screen_files)
    issue_count = sum(len(result[key]) for key in ("unknown_colors", "unloaded_fonts", "external_urls", "broken_paths"))
    next_step = ("Fix these or tell the user why they stay, then give the user the url" if issue_count
                 else "Give the user the full url and end your turn")
    if not result["has_tokens_css"]:
        next_step += ". No tokens.css yet: run tokens first unless this project has no design files"
    return emit({**result, "issue_count": issue_count, "screens_checked": [path.name for path in screen_files],
                 "summary": f"{issue_count} issue(s) in {len(screen_files)} mockup(s)", "next": next_step})
