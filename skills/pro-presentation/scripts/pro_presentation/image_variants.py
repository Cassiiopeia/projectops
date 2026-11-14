"""Screen copies of large images: originals untouched; small view/thumbnail images go in .presentation/images/ and the server sends them instead
PPT export embeds the original from disk. Lookup (find_variant) is stdlib; building (build_variants) needs Pillow
Standalone: python image_variants.py --deck D > one JSON result line (the server runs it with a Pillow-equipped Python)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

if __name__ == "__main__":  # package import path when run standalone (this file: scripts/pro_presentation/image_variants.py)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pro_presentation.settings import (EXPORTS_DIR_NAME, IMAGE_CACHE_DIR_NAME, IMAGE_SUFFIXES, RECORDINGS_DIR_NAME,
                                       STATE_DIR_NAME, THUMBNAIL_STEMS)

# Copy kind > max width (px). view: slide screen (1920 design + headroom for high-DPI), thumb: bottom thumbnail row
VARIANT_WIDTHS = {"view": 2560, "thumb": 320}
# Build a copy only when the original exceeds the target by more than this factor (slightly large images stay as is)
MINIMUM_SHRINK_RATIO = 1.25
JPEG_QUALITY = 88
# Copy extensions (opaque jpg, transparent png) · marker for originals that need no copy or cannot get one
VARIANT_SUFFIXES = (".jpg", ".png")
SKIP_SUFFIX = ".skip"
# Folders not searched for copies (relative to the deck root)
SKIPPED_TOP_DIRS = {STATE_DIR_NAME, EXPORTS_DIR_NAME, RECORDINGS_DIR_NAME}


def cache_dir(deck_dir: Path) -> Path:
    return deck_dir / STATE_DIR_NAME / IMAGE_CACHE_DIR_NAME


def variant_stem(deck_dir: Path, source: Path, kind: str) -> str | None:
    """Copy name: original path hash + mtime + size + kind (name changes when the original changes)"""
    try:
        stat = source.stat()
        relative = source.resolve().relative_to(deck_dir.resolve()).as_posix()
    except (OSError, ValueError):
        return None
    path_hash = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:16]
    return f"{path_hash}-{stat.st_mtime_ns:x}-{stat.st_size:x}-{kind}"


def find_variant(deck_dir: Path, source: Path, kind: str) -> tuple[Path | None, bool]:
    """(copy file, decided). decided False = not built yet (server requests a build)"""
    stem = variant_stem(deck_dir, source, kind)
    if stem is None:
        return None, True
    folder = cache_dir(deck_dir)
    for suffix in VARIANT_SUFFIXES:
        if (folder / f"{stem}{suffix}").is_file():
            return folder / f"{stem}{suffix}", True
    return None, (folder / f"{stem}{SKIP_SUFFIX}").is_file()


def wanted_variants(deck_dir: Path) -> list[tuple[Path, str]]:
    """Copies needed for each image in the deck (by slide folder). Thumbnails only for each slide's main image (original · slide)"""
    wanted = []
    for folder, directory_names, file_names in os.walk(deck_dir):
        if Path(folder) == deck_dir:
            directory_names[:] = [name for name in directory_names if name not in SKIPPED_TOP_DIRS]
        directory_names.sort()
        for name in sorted(file_names):
            path = Path(folder) / name
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            wanted.append((path, "view"))
            if path.stem in THUMBNAIL_STEMS:
                wanted.append((path, "thumb"))
    return wanted


def _write_variant(image_module, source: Path, target_stem: Path, width: int) -> bool:
    """Original > copy of the given width. False without building if already small enough"""
    with image_module.open(source) as image:
        if image.width <= width * MINIMUM_SHRINK_RATIO:
            return False
        image.draft("RGB", (width, width))   # jpg originals are downscaled while reading
        may_have_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
        height = max(1, round(image.height * width / image.width))
        resized = image.convert("RGBA" if may_have_alpha else "RGB").resize((width, height), image_module.LANCZOS)
    # Even with an alpha channel, use jpg if it is fully opaque (most imported PPT images)
    has_alpha = may_have_alpha and resized.getchannel("A").getextrema()[0] < 255
    if may_have_alpha and not has_alpha:
        resized = resized.convert("RGB")
    # Rename after writing completes: so the server never sends a half-written file
    suffix = ".png" if has_alpha else ".jpg"
    partial = target_stem.with_name(target_stem.name + ".part")
    if has_alpha:
        resized.save(partial, "PNG", optimize=True)
    else:
        resized.save(partial, "JPEG", quality=JPEG_QUALITY, optimize=True)
    os.replace(partial, target_stem.with_name(target_stem.name + suffix))
    return True


def build_variants(deck_dir: Path, limit: int | None = None) -> dict:
    """Build missing copies (up to limit, has_more if any remain) + delete copies whose original is gone"""
    from PIL import Image
    folder = cache_dir(deck_dir)
    folder.mkdir(parents=True, exist_ok=True)
    counts = {"built": 0, "skipped": 0, "failed": 0, "removed": 0, "has_more": False}
    current_stems = set()
    for source, kind in wanted_variants(deck_dir):
        stem = variant_stem(deck_dir, source, kind)
        if stem is None:
            continue
        current_stems.add(stem)
        if find_variant(deck_dir, source, kind) != (None, False):
            continue
        if limit is not None and counts["built"] >= limit:
            counts["has_more"] = True
            continue
        # Thumbnails shrink from the view copy just built (the large original is not read twice)
        pixel_source = (find_variant(deck_dir, source, "view")[0] or source) if kind == "thumb" else source
        try:
            is_built = _write_variant(Image, pixel_source, folder / stem, VARIANT_WIDTHS[kind])
        except Exception:  # broken or oversized image: mark to send the original and continue
            is_built = False
            counts["failed"] += 1
        if is_built:
            counts["built"] += 1
        else:
            (folder / f"{stem}{SKIP_SUFFIX}").touch()
            counts["skipped"] += 1
    for cached in folder.iterdir():
        if cached.stem not in current_stems:
            cached.unlink(missing_ok=True)
            counts["removed"] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deck", required=True)
    parser.add_argument("--limit", type=int, default=None, help="Build at most this many copies in one run")
    args = parser.parse_args()
    try:
        print(json.dumps({"ok": True, **build_variants(Path(args.deck).resolve(), args.limit)}))
    except ImportError:
        print(json.dumps({"ok": False, "code": "pillow_missing"}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
