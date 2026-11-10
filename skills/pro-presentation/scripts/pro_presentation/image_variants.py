"""큰 그림의 화면용 사본: 원본은 그대로 두고 .presentation/images/ 에 보기용 · 썸네일용 작은 그림을 만들어 서버가 대신 보냄
PPT 내보내기는 디스크의 원본을 그대로 넣음. 찾기(find_variant)는 표준 라이브러리, 만들기(build_variants)는 Pillow 필요
단독 실행: python image_variants.py --deck D > 결과 JSON 한 줄 (서버가 Pillow 있는 파이썬으로 실행)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

if __name__ == "__main__":  # 단독 실행 시 패키지 import 경로 (이 파일: scripts/pro_presentation/image_variants.py)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pro_presentation.settings import (EXPORTS_DIR_NAME, IMAGE_CACHE_DIR_NAME, IMAGE_SUFFIXES, RECORDINGS_DIR_NAME,
                                       STATE_DIR_NAME, THUMBNAIL_STEMS)

# 사본 종류 > 가로 최대 (px). view: 슬라이드 화면 (1920 설계 + 고해상도 화면 여유), thumb: 아래 썸네일 줄
VARIANT_WIDTHS = {"view": 2560, "thumb": 320}
# 원본이 목표보다 이 배율 넘게 클 때만 사본을 만듦 (조금 큰 그림은 원본 그대로)
MINIMUM_SHRINK_RATIO = 1.25
JPEG_QUALITY = 88
# 사본 확장자 (불투명 jpg, 투명 png) · 사본이 필요 없거나 만들 수 없는 원본 표시
VARIANT_SUFFIXES = (".jpg", ".png")
SKIP_SUFFIX = ".skip"
# 사본을 찾지 않는 폴더 (덱 최상위 기준)
SKIPPED_TOP_DIRS = {STATE_DIR_NAME, EXPORTS_DIR_NAME, RECORDINGS_DIR_NAME}


def cache_dir(deck_dir: Path) -> Path:
    return deck_dir / STATE_DIR_NAME / IMAGE_CACHE_DIR_NAME


def variant_stem(deck_dir: Path, source: Path, kind: str) -> str | None:
    """사본 이름: 원본 경로 해시 + 수정 시각 + 크기 + 종류 (원본이 바뀌면 이름이 바뀜)"""
    try:
        stat = source.stat()
        relative = source.resolve().relative_to(deck_dir.resolve()).as_posix()
    except (OSError, ValueError):
        return None
    path_hash = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:16]
    return f"{path_hash}-{stat.st_mtime_ns:x}-{stat.st_size:x}-{kind}"


def find_variant(deck_dir: Path, source: Path, kind: str) -> tuple[Path | None, bool]:
    """(사본 파일, 판정 끝남). 판정 끝남 False = 아직 만들지 않음 (서버가 만들기를 요청)"""
    stem = variant_stem(deck_dir, source, kind)
    if stem is None:
        return None, True
    folder = cache_dir(deck_dir)
    for suffix in VARIANT_SUFFIXES:
        if (folder / f"{stem}{suffix}").is_file():
            return folder / f"{stem}{suffix}", True
    return None, (folder / f"{stem}{SKIP_SUFFIX}").is_file()


def wanted_variants(deck_dir: Path) -> list[tuple[Path, str]]:
    """덱 안 그림마다 필요한 사본 (장 폴더 순). 썸네일은 장 대표 그림(original · slide)만"""
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
    """원본 > 가로 width 사본. 충분히 작으면 만들지 않고 False"""
    with image_module.open(source) as image:
        if image.width <= width * MINIMUM_SHRINK_RATIO:
            return False
        image.draft("RGB", (width, width))   # jpg 원본은 읽을 때부터 줄여 읽음
        may_have_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
        height = max(1, round(image.height * width / image.width))
        resized = image.convert("RGBA" if may_have_alpha else "RGB").resize((width, height), image_module.LANCZOS)
    # 투명 채널이 있어도 실제로 다 불투명하면 jpg (가져온 PPT 그림 대부분)
    has_alpha = may_have_alpha and resized.getchannel("A").getextrema()[0] < 255
    if may_have_alpha and not has_alpha:
        resized = resized.convert("RGB")
    # 다 쓴 뒤 이름 바꾸기: 서버가 쓰다 만 파일을 보내지 않게
    suffix = ".png" if has_alpha else ".jpg"
    partial = target_stem.with_name(target_stem.name + ".part")
    if has_alpha:
        resized.save(partial, "PNG", optimize=True)
    else:
        resized.save(partial, "JPEG", quality=JPEG_QUALITY, optimize=True)
    os.replace(partial, target_stem.with_name(target_stem.name + suffix))
    return True


def build_variants(deck_dir: Path, limit: int | None = None) -> dict:
    """없는 사본 만들기 (limit 개까지, 남으면 has_more) + 원본이 사라진 사본 지우기"""
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
        # 썸네일은 방금 만든 보기용 사본에서 줄임 (큰 원본을 두 번 읽지 않음)
        pixel_source = (find_variant(deck_dir, source, "view")[0] or source) if kind == "thumb" else source
        try:
            is_built = _write_variant(Image, pixel_source, folder / stem, VARIANT_WIDTHS[kind])
        except Exception:  # 깨진 그림 · 너무 큰 그림: 원본 그대로 보내도록 표시하고 계속
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
