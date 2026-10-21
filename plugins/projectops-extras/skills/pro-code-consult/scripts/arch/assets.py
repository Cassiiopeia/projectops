"""assets: 이미지·폰트 sha256 > 같은 내용 사본 묶음, 같은 이름·다른 내용 (낡은 사본 의심)

같은 이름 비교는 확장자가 같고(svg ↔ png 는 형식 차이), PNG 는 픽셀 크기까지 같은 것끼리만 한다.
"""
from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path

from .source_files import git_ignored_paths, walk_files

ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico",
                    ".ttf", ".otf", ".woff", ".woff2"}
# 웹폰트 형식 묶음 (ttf·woff·woff2 를 함께 두는 것은 정상 — 형식 변형 후보에서 뺌)
FONT_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2", ".eot"}
# 자산 최대 크기 (20MB — 그 이상은 원본 작업 파일로 보고 건너뜀)
MAXIMUM_ASSET_BYTES = 20 * 1024 * 1024
# 이름 정규화: 배율·크기 접미사 제거 (logo@2x, app_icon_1024 > logo, app_icon)
SIZE_SUFFIX_PATTERN = re.compile(r"(?:@\d(?:\.\d)?x|[-_]\d{2,4}(?:x\d{2,4})?|[-_](?:xx?x?h|m|h)dpi)$", re.IGNORECASE)

# 앱 아이콘 생성 도구가 만드는 영역 (flutter_launcher_icons 가 있으면 이 영역끼리의 사본은 생성 결과)
ICON_GENERATOR_AREAS = {"android_launcher", "ios_assets", "macos", "web_public", "windows"}
# 모듈 이름을 앞에 붙일 일반 영역 (client/assets 와 app/assets 를 다른 영역으로)
GENERIC_AREAS = {"app_assets", "other"}
# 플랫폼 영역 판별 (경로 일부 > 영역 이름) — 앞에서부터 처음 맞는 것
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

    # 해시 수집 (gitignore 대상 제외 — 스크린샷·증거 폴더는 레포 자산이 아니다)
    candidates = [(r, a) for r, a in walk_files(root) if Path(r).suffix.lower() in ASSET_EXTENSIONS]
    ignored = git_ignored_paths(root, [r for r, _ in candidates]) or set()
    for relative, absolute in candidates:
        if relative in ignored:
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
    # 판단할 것 먼저: 영역을 넘는 손복사 > 생성 결과·참고 자료 사본
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
    """같은 이름·같은 확장자(PNG 는 같은 픽셀 크기)가 2개 이상 영역에 다른 내용으로 있으면 의심

    한 영역 안의 크기별 변형은 정상. 확장자만 다른 같은 이름은 format_variants 로 따로 (안 쓰는 사본 후보)
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
    """PNG 머리(IHDR)의 가로·세로 (읽기 실패면 None)"""
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
