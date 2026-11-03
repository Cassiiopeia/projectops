"""store-pages: pages.json > 언어별 랜딩 페이지 + hreflang + sitemap.xml + robots.txt (#1021)

파일은 run_dir/store/site/ 아래에만 쓴다. 올리기(호스팅)는 하지 않는다.
결과: site/index.html(언어 선택) · site/{folder}/index.html · site/{folder}/images/ · site/fonts/ · sitemap.xml · robots.txt
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from common.emit import emit
from figma_tools.commands.compose import resolve_store_dir
from figma_tools.store_scenes import resolve_theme
from figma_tools.store_site import (
    alternate_links, build_locale_page, build_robots, build_root_page, build_sitemap,
)

PAGES_FILE_NAME = "pages.json"
SITE_SUBDIR = "site"
# 언어 폴더 = 주소 경로 한 칸 (영문·숫자·하이픈만)
_FOLDER_PATTERN = re.compile(r"^[A-Za-z0-9-]{2,20}$")
# hreflang: 언어(2~3자) + 선택 문자 체계(4자) + 선택 지역(2자 또는 숫자 3자)
_HREFLANG_PATTERN = re.compile(r"^[a-z]{2,3}(-[A-Z][a-z]{3})?(-([A-Z]{2}|\d{3}))?$")
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_IMAGE_COUNT = 5
DEFAULT_STORE_LABELS = {"app_store": "Download on the App Store", "play": "Get it on Google Play"}
REQUIRED_TEXT_KEYS = ("title", "description")


def _load_pages(path: Path) -> tuple[dict | None, dict | None]:
    if not path.is_file():
        return None, {"ok": False, "code": "pages_not_found", "error": f"{path} not found",
                      "hint": "Write pages.json there (format: references/store-assets.md §Landing pages)"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as read_error:
        return None, {"ok": False, "code": "pages_unreadable", "error": str(read_error)}
    if not isinstance(data, dict) or not isinstance(data.get("locales"), dict) or not data["locales"]:
        return None, {"ok": False, "code": "pages_invalid", "error": "pages.json needs a non-empty 'locales' object"}
    return data, None


def _normalized_base_url(raw: object) -> str | None:
    """https 절대 주소만 허용, 끝은 / 로 맞춘다"""
    if not isinstance(raw, str):
        return None
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        return None
    return raw if raw.endswith("/") else raw + "/"


def _validate_app(app: dict) -> list:
    issues = []
    for key in ("app_store_url", "play_url"):
        value = app.get(key)
        if value is not None and not (isinstance(value, str) and urlparse(value).scheme == "https"
                                      and urlparse(value).netloc):
            issues.append({"code": "store_url_invalid", "field": f"app.{key}", "message": f"app.{key} must be an https URL"})
    return issues


def _locale_images(images: dict | None, locale_entry: dict, folder: str) -> list[Path]:
    """스토어 이미지 폴더 규약({dir}/{store}/{locale}/{slot}/)에서 이 언어 스크린샷, 이름 순 max 장"""
    if not images:
        return []
    locale = locale_entry.get("image_locale") or folder
    slot_dir = Path(images["dir"]) / images["store"] / locale / images["slot"]
    if not slot_dir.is_dir():
        return []
    files = sorted(p for p in slot_dir.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES)
    return files[: int(images.get("max") or DEFAULT_IMAGE_COUNT)]


def _validate_images(images: object) -> tuple[dict | None, list]:
    if images is None:
        return None, []
    if not (isinstance(images, dict) and all(isinstance(images.get(k), str) for k in ("dir", "store", "slot"))):
        return None, [{"code": "images_invalid", "message": "images needs 'dir', 'store' and 'slot' strings"}]
    if not Path(images["dir"]).is_dir():
        return None, [{"code": "images_dir_missing", "message": f"images.dir not found: {images['dir']}"}]
    return images, []


def _build_pages(data: dict, images: dict | None) -> tuple[list, list, list]:
    """locales > 페이지 목록 + issues + warnings. 문제 있는 언어는 페이지에서 뺀다"""
    pages, issues, warnings, seen_hreflang = [], [], [], set()
    for folder, entry in data["locales"].items():
        if not isinstance(entry, dict):
            issues.append({"code": "pages_invalid", "locale": folder, "message": f"locales.{folder} must be an object"})
            continue
        hreflang = entry.get("hreflang") or folder
        problems = []
        if not _FOLDER_PATTERN.match(folder):
            problems.append({"code": "folder_invalid", "message": f"locale key {folder!r} must be letters, digits and '-'"})
        if not _HREFLANG_PATTERN.match(hreflang):
            problems.append({"code": "hreflang_invalid", "message": f"{hreflang!r} is not a language code like en, en-US, zh-Hant"})
        elif hreflang in seen_hreflang:
            problems.append({"code": "hreflang_duplicate", "message": f"hreflang {hreflang} is used twice"})
        for key in REQUIRED_TEXT_KEYS:
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                problems.append({"code": "text_missing", "message": f"locales.{folder}.{key} is empty"})
        if problems:
            issues.extend(dict(problem, locale=folder) for problem in problems)
            continue
        seen_hreflang.add(hreflang)
        labels = dict(DEFAULT_STORE_LABELS, **(entry.get("store_labels") or {}))
        if not entry.get("store_labels") and not hreflang.startswith("en"):
            warnings.append({"code": "store_label_default", "locale": folder,
                             "message": f"{folder} uses the English store link labels; add store_labels in that language"})
        image_files = _locale_images(images, entry, folder)
        if images and not image_files:
            warnings.append({"code": "images_missing", "locale": folder,
                             "message": f"No screenshots for {folder} under {images['dir']}/{images['store']}/"
                                        f"{entry.get('image_locale') or folder}/{images['slot']}"})
        features = [f for f in entry.get("features") or [] if isinstance(f, str) and f.strip()]
        pages.append({"folder": folder, "hreflang": hreflang, "language_name": entry.get("language_name") or folder,
                      "text": {**{k: entry[k] for k in REQUIRED_TEXT_KEYS},
                               "headline": entry.get("headline"), "subtitle": entry.get("subtitle"),
                               "features": features},
                      "store_labels": labels, "image_files": image_files,
                      "image_names": [f"{index:02d}{path.suffix.lower()}" for index, path in enumerate(image_files, 1)]})
    return pages, issues, warnings


def _write_site(site_dir: Path, pages: list, site: dict) -> list[str]:
    """페이지·이미지·글꼴·sitemap·robots 쓰기 > 쓴 파일 목록"""
    written = []

    def write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(str(path))

    for font in site["theme"]["font_files"]:
        target = site_dir / "fonts" / font["file_name"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(font["path"], target)
        written.append(str(target))
    for page in pages:
        page_dir = site_dir / page["folder"]
        for source, name in zip(page["image_files"], page["image_names"]):
            target = page_dir / "images" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            written.append(str(target))
        write(page_dir / "index.html", build_locale_page(page, pages, site))
    write(site_dir / "index.html", build_root_page(pages, site))
    write(site_dir / "sitemap.xml", build_sitemap(site, pages))
    write(site_dir / "robots.txt", build_robots(site["base_url"]))
    return written


def cmd_store_pages(args) -> int:
    """검증 > 언어별 페이지 + 언어 선택 + sitemap + robots 생성"""
    store_dir, error = resolve_store_dir(args.run_dir, Path(args.root).resolve())
    if error:
        return emit(error)
    data, error = _load_pages(Path(args.pages).resolve() if args.pages else store_dir / PAGES_FILE_NAME)
    if error:
        return emit(error)

    base_url = _normalized_base_url(data.get("base_url"))
    app = data.get("app") if isinstance(data.get("app"), dict) else {}
    theme, issues = resolve_theme(data.get("theme"))
    for index, font in enumerate(theme["font_files"], 1):
        font["file_name"] = f"font{index}{Path(font['path']).suffix.lower()}"
    if base_url is None:
        issues.append({"code": "base_url_invalid", "message": "base_url must be an absolute https URL without query"})
    issues.extend(_validate_app(app))
    images, image_issues = _validate_images(data.get("images"))
    issues.extend(image_issues)
    pages, page_issues, warnings = _build_pages(data, images)
    issues.extend(page_issues)
    default_folder = data.get("default_locale") or next(iter(data["locales"]))
    if default_folder not in {page["folder"] for page in pages}:
        issues.append({"code": "default_locale_missing",
                       "message": f"default_locale {default_folder!r} has no valid page (it is the x-default target)"})
    if issues:
        return emit({"verdict": "issues", "summary": f"{len(issues)} issue(s); nothing written",
                     "next": "Fix each item in issues in pages.json and run store-pages again",
                     "issues": issues, "warnings": warnings})

    site = {"base_url": base_url, "app": app, "theme": theme,
            "links": alternate_links(base_url, pages, default_folder)}
    site_dir = store_dir / SITE_SUBDIR
    try:
        written = _write_site(site_dir, pages, site)
    except OSError as os_error:
        return emit({"ok": False, "code": "write_failed", "error": str(os_error)})
    if urlparse(base_url).path not in ("", "/"):
        warnings.append({"code": "robots_not_at_root",
                         "message": "base_url has a path; crawlers read robots.txt only at the host root, so merge its Sitemap line there"})
    return emit({
        "verdict": "ready",
        "summary": f"{len(pages)} locale page(s) + language picker + sitemap.xml · {len(warnings)} warning(s)",
        "next": (f"Open {site_dir / pages[0]['folder'] / 'index.html'} with pro-launch web to review, "
                 f"then publish the {site_dir} folder at {base_url} (hosting is up to you)"),
        "site_dir": str(site_dir),
        "pages": [{"folder": page["folder"], "hreflang": page["hreflang"], "images": len(page["image_files"])}
                  for page in pages],
        "x_default": default_folder,
        "files": written,
        "warnings": warnings,
    })
