"""store-specs: 스토어 규격 정본 출력 / store-check: 이미지 폴더 > 슬롯·언어별 판정 (#884)

사실만 돌려준다. 어디서 다시 내보낼지·무엇을 고칠지는 에이전트가 판단한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common.emit import emit
from figma_tools.store_check import (
    GLOBAL_LOCALE, judge_slot, needed_slots, scan_store_folder,
)

STORE_SPECS_PATH = Path(__file__).resolve().parents[1] / "store_specs.json"
STORE_IDS = ("ios", "play")
LAYOUT_EXAMPLE = "<dir>/ios/en-US/iphone-dynamic-island-large/01.png, <dir>/play/_global/app-icon/icon.png"


def load_store_specs() -> dict:
    return json.loads(STORE_SPECS_PATH.read_text(encoding="utf-8"))


def cmd_store_specs(args) -> int:
    """정본 그대로 (--store 면 그 스토어만)"""
    specs = load_store_specs()
    stores = specs["stores"]
    if args.store:
        stores = {args.store: stores[args.store]}
    slot_count = sum(len(s["slots"]) for s in stores.values())
    return emit({
        "layout": specs["layout"],
        "requirement_values": specs["requirement_values"],
        "stores": stores,
        "spec_file": str(STORE_SPECS_PATH),
        "summary": f"{slot_count} slot(s) in {', '.join(stores)}; each value carries source_url and checked_at",
        "next": ("Compare your store frames with these sizes, export them into the layout "
                 f"({LAYOUT_EXAMPLE}), then run store-check --dir <dir>"),
    })


# =========================================================================
# 목표 언어: --locales > version.yml store_locales_{store} > store_locales > 폴더
# =========================================================================

def _read_inline_list(version_yml_text: str, key: str) -> list[str] | None:
    """options.<key>: [a, b] 인라인 배열 (.github/scripts/store_notes.py 와 같은 표기). 없으면 None"""
    for line in version_yml_text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = re.match(rf"^\s+{key}:\s*\[([^\]]*)\]", line)
        if match:
            values = [v.strip().strip("\"'") for v in match.group(1).split(",")]
            return [v for v in values if v]
    return None


def resolve_target_locales(store: str, cli_locales: str | None, project_root: Path,
                           folder_locales: list[str]) -> tuple[list[str], str]:
    """(목표 언어 목록, 출처) — 출처: cli / version.yml:<키> / folder"""
    if cli_locales:
        return [v.strip() for v in cli_locales.split(",") if v.strip()], "cli"
    version_yml = project_root / "version.yml"
    if version_yml.is_file():
        text = version_yml.read_text(encoding="utf-8", errors="replace")
        for key in (f"store_locales_{store}", "store_locales"):
            values = _read_inline_list(text, key)
            if values:
                return values, f"version.yml:{key}"
    return sorted(folder_locales), "folder"


def _language_part(locale: str) -> str:
    return locale.replace("_", "-").split("-")[0].lower()


def _locale_code_mismatches(store: str, targets: list[str], folder_locales: list[str]) -> list:
    """폴더 이름이 목표와 언어만 같고 코드가 다름 (ko <-> ko-KR) > 경고. 변환은 하지 않음"""
    warnings = []
    for folder_locale in folder_locales:
        if folder_locale in targets:
            continue
        for target in targets:
            if target not in folder_locales and _language_part(target) == _language_part(folder_locale):
                warnings.append({"code": "locale_code_mismatch", "store": store, "locale": folder_locale,
                                 "expected": target,
                                 "message": (f"folder {store}/{folder_locale} does not match target locale "
                                             f"{target} (same language, different code). Use the exact code "
                                             f"this store uses for both, see locale_codes in store-specs")})
    return warnings


# =========================================================================
# store-check
# =========================================================================

def cmd_store_check(args) -> int:
    """폴더 훑기 > 스토어별 판정 > verdict"""
    root = Path(args.dir).resolve()
    if not root.is_dir():
        return emit({"ok": False, "code": "dir_not_found", "error": f"Folder not found: {args.dir}",
                     "hint": f"Export images into the layout first: {LAYOUT_EXAMPLE}"})
    specs = load_store_specs()
    found, unknown = scan_store_folder(root, specs)
    project_root = Path(args.root).resolve()

    matrix, issues, warnings, locales_by_store = {}, [], [], {}
    for store, store_found in found.items():
        store_report = _judge_store(store, specs["stores"][store], store_found, args.locales,
                                    project_root, root)
        matrix[store] = store_report["matrix"]
        issues.extend(store_report["issues"])
        warnings.extend(store_report["warnings"])
        locales_by_store[store] = store_report["locales"]

    image_count = sum(len(images) for store_found in found.values()
                      for slots in store_found.values() for images in slots.values())
    verdict = "empty" if image_count == 0 else ("issues" if issues else "ready")
    return emit({
        "verdict": verdict,
        "summary": _summary(verdict, image_count, issues, warnings, unknown),
        "next": _next_step(verdict),
        "dir": str(root),
        "image_count": image_count,
        "locales": locales_by_store,
        "issues": issues,
        "warnings": warnings,
        "unknown": unknown,
        "matrix": matrix,
    })


def _judge_store(store: str, store_spec: dict, store_found: dict, cli_locales: str | None,
                 project_root: Path, root: Path) -> dict:
    """스토어 1개 > 언어별·슬롯별 판정 + 빠진 필수 슬롯"""
    folder_locales = [loc for loc in store_found if loc != GLOBAL_LOCALE]
    targets, source = resolve_target_locales(store, cli_locales, project_root, folder_locales)
    base_locale = targets[0] if targets and source != "folder" else None
    is_fallback_confirmed = store_spec.get("fallback_to_base") is True

    issues, warnings = [], _locale_code_mismatches(store, targets, folder_locales)
    matrix: dict = {}
    # 판정 대상: 목표 언어 + 폴더에만 있는 언어(파일 검사만) + _global
    judged_locales = targets + [loc for loc in folder_locales if loc not in targets] + [GLOBAL_LOCALE]
    for locale in judged_locales:
        is_global = locale == GLOBAL_LOCALE
        locale_found = store_found.get(locale, {})
        is_target = is_global or locale in targets
        if not is_target:
            warnings.append({"code": "locale_not_targeted", "store": store, "locale": locale,
                             "message": f"{store}/{locale} is not in the target locales ({source}); files checked only"})
        locale_matrix = {}
        for slot_id, images in locale_found.items():
            if not images:
                continue
            cell = judge_slot(images, store_spec["slots"][slot_id], root)
            locale_matrix[slot_id] = cell
            for problem in cell["problems"]:
                issues.append(dict(problem, store=store, locale=locale, slot=slot_id))
            for file_entry in cell["files"]:
                for problem in file_entry["problems"]:
                    issues.append(dict(problem, store=store, locale=locale, slot=slot_id, file=file_entry["file"]))
                for warning in file_entry.get("warnings", []):
                    warnings.append(dict(warning, store=store, locale=locale, slot=slot_id, file=file_entry["file"]))
            for warning in cell["warnings"]:
                warnings.append(dict(warning, store=store, locale=locale, slot=slot_id))
        if is_target:
            missing = needed_slots(store_spec, store_found, locale_found, is_global)
            for key, reason in missing.items():
                locale_matrix[key] = {"status": "missing", "count": 0, "reason": reason}
                entry = {"store": store, "locale": locale, "slot": key,
                         "message": f"{store}/{locale}: {key} has no images ({reason})"}
                is_base_or_global = is_global or locale == base_locale
                if is_base_or_global or not is_fallback_confirmed:
                    issues.append(dict(entry, code="missing_slot"))
                else:
                    warnings.append(dict(entry, code="missing_slot_fallback",
                                         message=entry["message"] + "; the store shows the base locale images"))
        if locale_matrix or is_target and not is_global:
            matrix[locale] = locale_matrix
    return {"matrix": matrix, "issues": issues, "warnings": warnings,
            "locales": {"targets": targets, "source": source, "base": base_locale,
                        "fallback_to_base": store_spec.get("fallback_to_base")}}


def _summary(verdict: str, image_count: int, issues: list, warnings: list, unknown: list) -> str:
    if verdict == "empty":
        return f"No images to check ({len(unknown)} unknown entr{'y' if len(unknown) == 1 else 'ies'})"
    head = "Ready: every image matches the store specs" if verdict == "ready" else f"{len(issues)} issue(s) to fix"
    return f"{head} · {image_count} image(s) · {len(warnings)} warning(s) · {len(unknown)} unknown"


def _next_step(verdict: str) -> str:
    if verdict == "empty":
        return (f"Export images into the layout ({LAYOUT_EXAMPLE}); run store-specs for slot ids and sizes")
    if verdict == "issues":
        return ("Fix each item in issues at its source (the Figma frame or export scale), export again "
                "into the same folder, and run store-check again. Do not resize the exported files")
    return ("Write the upload checklist from matrix (store x locale x slot) into the folder from "
            "get-output-path; review warnings before uploading")
