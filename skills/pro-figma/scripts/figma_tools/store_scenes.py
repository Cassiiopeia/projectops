"""scenes.json 읽기 > 검증 > 렌더 작업(job) 목록 (#1021)

규격 숫자는 store_specs.json 단독 소유 — 여기서는 장면 파일이 규격 안에 있는지만 본다.
검증 실패는 예외가 아니라 issues 로 모아서 돌려준다 (한 번에 전부 고치게).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from figma_tools.store_check import find_size_problems

CAPTION_LAYOUTS = ("caption-top", "caption-bottom")   # 기기 틀 + 문구 (세로 슬롯)
BANNER_LAYOUT = "banner"                              # 문구만 (+ 선택 아이콘, 가로 슬롯)
LAYOUTS = CAPTION_LAYOUTS + (BANNER_LAYOUT,)
LOCALE_PLACEHOLDER = "{locale}"

_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_FONT_FAMILY_PATTERN = re.compile(r"^[\w \-,'\"]{1,120}$")
DEFAULT_THEME = {"background": "#0b1d3a", "foreground": "#ffffff", "accent": "#4da3ff",
                 "font_family": "sans-serif", "font_files": []}


def load_scenes(path: Path) -> tuple[dict | None, list]:
    """scenes.json > (dict, issues). 읽기·구조 오류면 dict 는 None"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [{"code": "scenes_not_found", "message": f"Scenes file not found: {path}"}]
    except (OSError, ValueError) as error:
        return None, [{"code": "scenes_unreadable", "message": f"Cannot read {path}: {error}"}]
    if not isinstance(data, dict) or not isinstance(data.get("outputs"), list) \
            or not isinstance(data.get("scenes"), list):
        return None, [{"code": "scenes_invalid",
                       "message": "Scenes file must be an object with 'outputs' (list) and 'scenes' (list)"}]
    return data, []


def resolve_theme(raw_theme: object) -> tuple[dict, list]:
    """테마 병합 + CSS 로 들어가는 값 검증 (색·글꼴 이름은 허용 문자만)"""
    theme = dict(DEFAULT_THEME)
    issues: list = []
    if not isinstance(raw_theme, dict):
        return theme, issues
    for key in ("background", "foreground", "accent"):
        if key in raw_theme:
            if isinstance(raw_theme[key], str) and _COLOR_PATTERN.match(raw_theme[key]):
                theme[key] = raw_theme[key]
            else:
                issues.append({"code": "theme_invalid", "message": f"theme.{key} must be a #hex color"})
    if "font_family" in raw_theme:
        if isinstance(raw_theme["font_family"], str) and _FONT_FAMILY_PATTERN.match(raw_theme["font_family"]):
            theme["font_family"] = raw_theme["font_family"]
        else:
            issues.append({"code": "theme_invalid", "message": "theme.font_family has characters that are not allowed"})
    for font in raw_theme.get("font_files") or []:
        family, font_path = (font.get("family"), font.get("path")) if isinstance(font, dict) else (None, None)
        if not (isinstance(family, str) and _FONT_FAMILY_PATTERN.match(family) and isinstance(font_path, str)):
            issues.append({"code": "theme_invalid", "message": "theme.font_files entries need 'family' and 'path'"})
        elif not Path(font_path).is_file():
            issues.append({"code": "font_missing", "message": f"Font file not found: {font_path}"})
        else:
            theme["font_files"].append({"family": family, "path": font_path})
    return theme, issues


def collect_scene_locales(scenes: list) -> list[str]:
    """장면 문구에 등장하는 언어 (등장 순서). 목표 언어를 못 정할 때의 마지막 출처"""
    locales: list[str] = []
    for scene in scenes:
        for locale in (scene.get("text") or {}):
            if locale not in locales:
                locales.append(locale)
    return locales


def build_jobs(data: dict, specs: dict, locales_by_store: dict, only_store: str | None) -> tuple[list, list]:
    """outputs x 장면 x 언어 > 작업 목록 + issues. 문제 있는 조합은 작업에서 뺀다"""
    scenes_by_id = {scene.get("id"): scene for scene in data["scenes"] if isinstance(scene, dict)}
    jobs: list = []
    issues: list = []
    for output in data["outputs"]:
        store, slot_id = output.get("store"), output.get("slot")
        if only_store and store != only_store:
            continue
        slot_spec = (specs["stores"].get(store) or {}).get("slots", {}).get(slot_id)
        if slot_spec is None:
            issues.append({"code": "slot_unknown", "store": store, "slot": slot_id,
                           "message": f"Unknown store/slot: {store}/{slot_id} (run store-specs for the ids)"})
            continue
        size = _resolve_size(output, slot_spec, issues, store, slot_id)
        if size is None:
            continue
        localized_locales = locales_by_store.get(store, []) if slot_spec["localized"] else ["_global"]
        for scene_index, scene_id in enumerate(output.get("scenes") or [], start=1):
            scene = scenes_by_id.get(scene_id)
            if scene is None:
                issues.append({"code": "scene_unknown", "store": store, "slot": slot_id, "scene": scene_id,
                               "message": f"Scene '{scene_id}' is not defined in scenes"})
                continue
            for locale in localized_locales:
                job = _build_job(store, slot_id, size, scene, scene_index, locale, issues)
                if job:
                    jobs.append(job)
    return jobs, issues


def _resolve_size(output: dict, slot_spec: dict, issues: list, store: str, slot_id: str) -> list | None:
    """output.size 가 슬롯 규격 안인지 확인. 허용 목록이 하나뿐이면 생략 가능, 범위형은 필수"""
    size = output.get("size")
    exact_sizes = slot_spec["size"].get("exact")
    if size is None and exact_sizes and len(exact_sizes) == 1:
        size = exact_sizes[0]
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) for v in size)):
        issues.append({"code": "size_required", "store": store, "slot": slot_id,
                       "message": f"{store}/{slot_id}: set outputs[].size as [width, height] (see store-specs)"})
        return None
    size_problems = find_size_problems(size[0], size[1], slot_spec["size"])
    issues.extend(dict(problem, store=store, slot=slot_id) for problem in size_problems)
    return None if size_problems else size


def _build_job(store: str, slot_id: str, size: list, scene: dict, scene_index: int,
               locale: str, issues: list) -> dict | None:
    scene_id = scene.get("id")
    where = {"store": store, "slot": slot_id, "scene": scene_id, "locale": locale}
    layout = scene.get("layout", CAPTION_LAYOUTS[0])
    if layout not in LAYOUTS:
        issues.append(dict(where, code="layout_unknown", message=f"layout must be one of {', '.join(LAYOUTS)}"))
        return None
    is_portrait = size[1] > size[0]
    if (layout in CAPTION_LAYOUTS) != is_portrait:
        issues.append(dict(where, code="layout_size_mismatch",
                           message=f"{layout} needs a {'portrait' if layout in CAPTION_LAYOUTS else 'landscape'} "
                                   f"size, got {size[0]}x{size[1]}"))
        return None
    text = (scene.get("text") or {}).get(locale) if locale != "_global" else None
    if locale != "_global" and not (isinstance(text, dict) and text.get("title")):
        issues.append(dict(where, code="text_missing",
                           message=f"scene '{scene_id}' has no text.{locale}.title"))
        return None
    screenshot_path = None
    if layout in CAPTION_LAYOUTS:
        template = scene.get("screenshot", "")
        screenshot_path = Path(template.replace(LOCALE_PLACEHOLDER, locale)) if template else None
        if screenshot_path is None or not screenshot_path.is_file():
            issues.append(dict(where, code="screenshot_missing",
                               message=f"app capture not found: {screenshot_path or '(scene.screenshot unset)'}"))
            return None
    icon_path = Path(scene["icon"]) if scene.get("icon") else None
    if icon_path is not None and not icon_path.is_file():
        issues.append(dict(where, code="icon_missing", message=f"icon not found: {icon_path}"))
        return None
    return {"id": f"{store}/{locale}/{slot_id}/{scene_index:02d}", "store": store, "locale": locale,
            "slot": slot_id, "width": size[0], "height": size[1], "layout": layout,
            "title": (text or {}).get("title", ""), "subtitle": (text or {}).get("subtitle", ""),
            "screenshot": str(screenshot_path) if screenshot_path else None,
            "icon": str(icon_path) if icon_path else None, "file_name": f"{scene_index:02d}"}
