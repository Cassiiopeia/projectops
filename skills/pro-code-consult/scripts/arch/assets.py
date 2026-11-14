"""assets: image/font sha256 > groups of same-content copies, same name with different content (suspected stale copy)

Same-name comparison only pairs files with the same extension (svg ↔ png is a format difference), and PNGs only with the same pixel size.
"""
from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path

from .source_files import git_ignored_paths, walk_files

ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico",
                    ".ttf", ".otf", ".woff", ".woff2"}
# Web font format group (keeping ttf/woff/woff2 together is normal — excluded from format-variant candidates)
FONT_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2", ".eot"}
# Max asset size (20MB — larger files are treated as source work files and skipped)
MAXIMUM_ASSET_BYTES = 20 * 1024 * 1024
# Name normalization: strip scale/size suffixes (logo@2x, app_icon_1024 > logo, app_icon)
SIZE_SUFFIX_PATTERN = re.compile(r"(?:@\d(?:\.\d)?x|[-_]\d{2,4}(?:x\d{2,4})?|[-_](?:xx?x?h|m|h)dpi)$", re.IGNORECASE)

# Areas written by app icon generators (with flutter_launcher_icons, copies between these areas are generated output)
ICON_GENERATOR_AREAS = {"android_launcher", "ios_assets", "macos", "web_public", "windows"}
# Generic areas prefixed with the module name (client/assets and app/assets count as different areas)
GENERIC_AREAS = {"app_assets", "other"}
# Platform area detection (path fragment > area name) — first match wins
PLATFORM_AREA_MARKERS = (
    ("/res/mipmap", "android_launcher"), ("/res/drawable", "android_drawable"),
    ("/macos/", "macos"), ("/windows/", "windows"), ("/linux/", "linux"),
    (".xcassets/", "ios_assets"), ("/ios/", "ios"), ("/android/", "android"),
    ("/static/", "server_static"), ("/templates/", "server_templates"),
    ("/public/", "web_public"), ("assets/", "app_assets"),
)


def scan_assets(root: Path, limit: int) -> dict:
    files_by_hash: dict[str, list[str]] = {}
    sizes: dict[str, int] = {}

    # Collect hashes (skip gitignored paths — screenshot/evidence folders are not repo assets)
    candidates = [(r, a) for r, a in walk_files(root) if Path(r).suffix.lower() in ASSET_EXTENSIONS]
    ignored = git_ignored_paths(root, [r for r, _ in candidates]) or set()
    for relative, absolute in candidates:
        if relative in ignored:
            continue
        try:
            size = absolute.stat().st_size
            if size > MAXIMUM_ASSET_BYTES:
                continue
            digest = file_sha256(absolute)
        except OSError:
            continue
        files_by_hash.setdefault(digest, []).append(relative)
        sizes[digest] = size

    has_icon_generator = _has_icon_generator(root)
    copies = []
    for digest, paths in files_by_hash.items():
        if len(paths) < 2:
            continue
        areas = sorted({platform_area(p) for p in paths})
        group = {"sha256": digest[:12], "bytes": sizes[digest], "paths": paths, "areas": areas}
        if has_icon_generator and set(areas) <= ICON_GENERATOR_AREAS:
            group["is_generated_icon_set"] = True
        if any(p.startswith("docs/") or "/figma/" in "/" + p for p in paths):
            group["is_reference_copy"] = True
        copies.append(group)
    # Items needing judgment first: hand copies across areas > generated output and reference-material copies
    copies.sort(key=lambda g: (g.get("is_generated_icon_set", False) or g.get("is_reference_copy", False),
                               -len(g["areas"]), -len(g["paths"])))
    drift, format_variants = _same_name_different_content(root, files_by_hash)

    return {
        "assets_scanned": sum(len(p) for p in files_by_hash.values()),
        "ignored_assets": len(ignored),
        "identical_copies": copies[:limit],
        "same_name_different_content": drift[:limit],
        "format_variants": {"count": len(format_variants), "examples": format_variants[:10]},
        "truncated": {k: n for k, n in (("identical_copies", len(copies)),
                                        ("same_name_different_content", len(drift))) if n > limit},
        "summary": f"copy groups {len(copies)} (incl. {sum(1 for g in copies if g.get('is_generated_icon_set') or g.get('is_reference_copy'))} generated/reference copies), same name different content {len(drift)}, same name different format {len(format_variants)}",
    }


def file_sha256(path: Path) -> str:
    """File content hash (shared by assets copy groups and copies --file)"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def platform_area(relative: str) -> str:
    probe = "/" + relative
    area = next((a for marker, a in PLATFORM_AREA_MARKERS if marker in probe), "other")
    if area in GENERIC_AREAS and "/" in relative:
        return f"{relative.split('/', 1)[0]}:{area}"
    return area


def normalized_asset_name(relative: str) -> str:
    stem = Path(relative).stem.lower()
    previous = None
    while previous != stem:
        previous, stem = stem, SIZE_SUFFIX_PATTERN.sub("", stem)
    return stem


def _same_name_different_content(root: Path, files_by_hash: dict):
    """Suspect when the same name and extension (same pixel size for PNG) exists in 2+ areas with different content

    Size variants within one area are normal. Same name with only a different extension goes to format_variants (unused-copy candidates)
    """
    variants_by_key: dict[tuple, dict[str, list[str]]] = {}
    extensions_by_name: dict[str, set] = {}
    for digest, paths in files_by_hash.items():
        for path in paths:
            name, extension = normalized_asset_name(path), Path(path).suffix.lower()
            extensions_by_name.setdefault(name, set()).add(extension)
            size = _png_size(root / path) if extension == ".png" else None
            variants_by_key.setdefault((name, extension, size), {}).setdefault(digest, []).append(path)
    suspects = []
    for (name, extension, size), variants in variants_by_key.items():
        if len(variants) < 2 or len(name) < 3:
            continue
        areas = {platform_area(p) for paths in variants.values() for p in paths}
        if len(areas) < 2:
            continue
        suspect = {"name": name + extension, "areas": sorted(areas),
                   "variants": [{"sha256": d[:12], "paths": p} for d, p in variants.items()]}
        if size:
            suspect["pixels"] = f"{size[0]}x{size[1]}"
        suspects.append(suspect)
    suspects.sort(key=lambda s: -len(s["variants"]))
    format_variants = sorted(f"{n} ({', '.join(sorted(e))})" for n, e in extensions_by_name.items()
                             if len(e) > 1 and len(n) >= 3 and not e <= FONT_EXTENSIONS)
    return suspects, format_variants


def _png_size(path: Path):
    """Width and height from the PNG header (IHDR); None if unreadable"""
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def _has_icon_generator(root: Path) -> bool:
    for relative, absolute in walk_files(root):
        if absolute.name == "pubspec.yaml":
            try:
                if "flutter_launcher_icons" in absolute.read_text(encoding="utf-8", errors="replace"):
                    return True
            except OSError:
                continue
    return False
