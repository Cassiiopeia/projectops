"""assets: 이미지·폰트 sha256 > 같은 내용 사본 묶음, 같은 이름·다른 내용 (낡은 사본 의심)"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .source_files import walk_files

ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico",
                    ".ttf", ".otf", ".woff", ".woff2"}
# 자산 최대 크기 (20MB — 그 이상은 원본 작업 파일로 보고 건너뜀)
MAXIMUM_ASSET_BYTES = 20 * 1024 * 1024
# 이름 정규화: 배율·크기 접미사 제거 (logo@2x, app_icon_1024 > logo, app_icon)
SIZE_SUFFIX_PATTERN = re.compile(r"(?:@\d(?:\.\d)?x|[-_]\d{2,4}(?:x\d{2,4})?|[-_](?:xx?x?h|m|h)dpi)$", re.IGNORECASE)

# 플랫폼 영역 판별 (경로 일부 > 영역 이름) — 앞에서부터 처음 맞는 것
PLATFORM_AREA_MARKERS = (
    ("/res/mipmap", "android_launcher"), ("/res/drawable", "android_drawable"),
    (".xcassets/", "ios_assets"), ("/ios/", "ios"), ("/android/", "android"),
    ("/static/", "server_static"), ("/templates/", "server_templates"),
    ("/public/", "web_public"), ("assets/", "app_assets"),
)


def scan_assets(root: Path, limit: int) -> dict:
    files_by_hash: dict[str, list[str]] = {}
    sizes: dict[str, int] = {}

    # 해시 수집
    for relative, absolute in walk_files(root):
        if Path(relative).suffix.lower() not in ASSET_EXTENSIONS:
            continue
        try:
            size = absolute.stat().st_size
            if size > MAXIMUM_ASSET_BYTES:
                continue
            digest = hashlib.sha256(absolute.read_bytes()).hexdigest()
        except OSError:
            continue
        files_by_hash.setdefault(digest, []).append(relative)
        sizes[digest] = size

    copies = [{"sha256": digest[:12], "bytes": sizes[digest], "paths": paths,
               "areas": sorted({platform_area(p) for p in paths})}
              for digest, paths in files_by_hash.items() if len(paths) > 1]
    copies.sort(key=lambda group: -len(group["paths"]))
    drift = _same_name_different_content(files_by_hash)

    return {
        "assets_scanned": sum(len(p) for p in files_by_hash.values()),
        "identical_copies": copies[:limit],
        "same_name_different_content": drift[:limit],
        "truncated": {k: n for k, n in (("identical_copies", len(copies)),
                                        ("same_name_different_content", len(drift))) if n > limit},
        "summary": f"사본 묶음 {len(copies)}, 같은 이름·다른 내용 {len(drift)}",
    }


def platform_area(relative: str) -> str:
    probe = "/" + relative
    for marker, area in PLATFORM_AREA_MARKERS:
        if marker in probe:
            return area
    return "other"


def normalized_asset_name(relative: str) -> str:
    stem = Path(relative).stem.lower()
    previous = None
    while previous != stem:
        previous, stem = stem, SIZE_SUFFIX_PATTERN.sub("", stem)
    return stem


def _same_name_different_content(files_by_hash: dict) -> list[dict]:
    """같은 정규화 이름이 2개 이상 영역에 다른 내용으로 있으면 의심 (한 영역 안의 크기별 변형은 정상)"""
    variants_by_name: dict[str, dict[str, list[str]]] = {}
    for digest, paths in files_by_hash.items():
        for path in paths:
            variants_by_name.setdefault(normalized_asset_name(path), {}).setdefault(digest, []).append(path)
    suspects = []
    for name, variants in variants_by_name.items():
        if len(variants) < 2 or len(name) < 3:
            continue
        areas = {platform_area(p) for paths in variants.values() for p in paths}
        if len(areas) < 2:
            continue
        suspects.append({"name": name, "areas": sorted(areas),
                         "variants": [{"sha256": d[:12], "paths": p} for d, p in variants.items()]})
    suspects.sort(key=lambda s: -len(s["variants"]))
    return suspects
