"""Store image verdict: scan folders > per-file spec > per-slot count > required slots per language

Spec values are owned solely by store_specs.json — no numbers written here.
Judges only. Does not fix, resize or upload.
"""
from __future__ import annotations

from pathlib import Path

from figma_tools.image_header import read_image_header

GLOBAL_LOCALE = "_global"
IMAGE_EXTENSION_FORMATS = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg"}


def scan_store_folder(root: Path, specs: dict) -> tuple[dict, list]:
    """{root}/{store}/{locale}/{slot}/*.img > found[store][locale][slot] = [Path], unknown list"""
    found: dict = {}
    unknown: list = []
    for store_dir in sorted(root.iterdir()):
        if not store_dir.is_dir():
            unknown.append(_unknown(store_dir, root, "file outside {store}/{locale}/{slot}/"))
            continue
        store_spec = specs["stores"].get(store_dir.name)
        if store_spec is None:
            unknown.append(_unknown(store_dir, root,
                                    f"unknown store folder (known: {', '.join(specs['stores'])})"))
            continue
        store_found = found.setdefault(store_dir.name, {})
        for locale_dir in sorted(store_dir.iterdir()):
            if not locale_dir.is_dir():
                unknown.append(_unknown(locale_dir, root, "file outside {store}/{locale}/{slot}/"))
                continue
            _scan_locale(locale_dir, root, store_spec, store_found, unknown)
    return found, unknown


def _scan_locale(locale_dir: Path, root: Path, store_spec: dict, store_found: dict, unknown: list) -> None:
    """One language folder > slot folders (language-independent slots only in _global)"""
    is_global = locale_dir.name == GLOBAL_LOCALE
    for slot_dir in sorted(locale_dir.iterdir()):
        slot_spec = store_spec["slots"].get(slot_dir.name)
        if not slot_dir.is_dir():
            unknown.append(_unknown(slot_dir, root, "file outside {store}/{locale}/{slot}/"))
            continue
        if slot_spec is None:
            unknown.append(_unknown(slot_dir, root,
                                    f"unknown slot (known: {', '.join(store_spec['slots'])})"))
            continue
        if slot_spec["localized"] == is_global:
            reason = (f"slot {slot_dir.name} is per-language; put it under {{store}}/{{locale}}/"
                      if is_global else
                      f"slot {slot_dir.name} is not per-language; put it under {{store}}/{GLOBAL_LOCALE}/")
            unknown.append(_unknown(slot_dir, root, reason))
            continue
        images = []
        for entry in sorted(slot_dir.iterdir()):
            if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSION_FORMATS:
                images.append(entry)
            elif not entry.name.startswith("."):
                unknown.append(_unknown(entry, root, "not a .png/.jpg/.jpeg file directly in the slot folder"))
        store_found.setdefault(locale_dir.name, {})[slot_dir.name] = images


def _unknown(path: Path, root: Path, reason: str) -> dict:
    return {"path": str(path.relative_to(root)), "reason": reason}


def check_image_file(path: Path, slot_spec: dict) -> tuple[dict, list, list]:
    """One file > (read result, problem list, warning list). 5 checks: read, format, extension, alpha, size·bytes"""
    header = read_image_header(path)
    problems: list = []
    warnings: list = []
    if "error" in header:
        problems.append({"code": "unreadable_image", "message": header["error"]})
        return header, problems, warnings
    if header["format"] not in slot_spec["formats"]:
        problems.append({"code": "format_not_allowed",
                         "message": f"{header['format']} is not allowed (allowed: {', '.join(slot_spec['formats'])})"})
    if IMAGE_EXTENSION_FORMATS[path.suffix.lower()] != header["format"]:
        problems.append({"code": "extension_mismatch",
                         "message": f"file extension {path.suffix} but the content is {header['format']}"})
    if slot_spec.get("alpha") == "forbidden" and header["has_alpha"]:
        problems.append({"code": "alpha_not_allowed",
                         "message": "image has an alpha channel or transparency; export without alpha"})
    problems.extend(find_size_problems(header["width"], header["height"], slot_spec["size"]))
    max_bytes = slot_spec.get("max_bytes")
    if max_bytes and path.stat().st_size > max_bytes:
        problems.append({"code": "file_too_large",
                         "message": f"{path.stat().st_size} bytes, limit {max_bytes} bytes"})
    recommended_min_side = (slot_spec.get("recommended") or {}).get("min_side")
    if recommended_min_side and min(header["width"], header["height"]) < recommended_min_side:
        warnings.append({"code": "below_recommended_size",
                         "message": f"shorter side under the recommended {recommended_min_side}px"})
    return header, problems, warnings


def find_size_problems(width: int, height: int, size_rule: dict) -> list:
    """2 size rules: exact (allowed list) / range (edge length + long:short edge ratio)"""
    if "exact" in size_rule:
        if [width, height] in size_rule["exact"]:
            return []
        allowed = ", ".join(f"{w}x{h}" for w, h in size_rule["exact"])
        return [{"code": "size_not_allowed", "message": f"{width}x{height} is not accepted (accepted: {allowed})"}]
    size_range = size_rule["range"]
    problems = []
    shorter_side, longer_side = min(width, height), max(width, height)
    if shorter_side < size_range["min_side"] or longer_side > size_range["max_side"]:
        problems.append({"code": "side_out_of_range",
                         "message": f"{width}x{height}: each side must be {size_range['min_side']}-{size_range['max_side']}px"})
    if longer_side > shorter_side * size_range["max_aspect_ratio"]:
        problems.append({"code": "aspect_ratio_too_large",
                         "message": f"{width}x{height}: longer side over {size_range['max_aspect_ratio']}x the shorter side"})
    return problems


def judge_slot(images: list, slot_spec: dict, root: Path) -> dict:
    """One slot > {status, count, files, problems, warnings} (including count range)"""
    files, slot_problems, slot_warnings = [], [], []
    for image in images:
        header, problems, warnings = check_image_file(image, slot_spec)
        entry = {"file": str(image.relative_to(root)), "problems": problems}
        if "width" in header:
            entry.update(width=header["width"], height=header["height"], format=header["format"])
        if warnings:
            entry["warnings"] = warnings
        files.append(entry)
    count = len(images)
    if count < slot_spec["min_count"]:
        slot_problems.append({"code": "too_few", "message": f"{count} image(s), at least {slot_spec['min_count']}"})
    if count > slot_spec["max_count"]:
        slot_problems.append({"code": "too_many", "message": f"{count} image(s), at most {slot_spec['max_count']}"})
    recommended_min_count = (slot_spec.get("recommended") or {}).get("min_count")
    if recommended_min_count and count < recommended_min_count:
        slot_warnings.append({"code": "below_recommended_count",
                              "message": f"{count} image(s), {recommended_min_count} recommended"})
    has_problem = slot_problems or any(f["problems"] for f in files)
    return {"status": "issues" if has_problem else "ok", "count": count, "files": files,
            "problems": slot_problems, "warnings": slot_warnings}


def needed_slots(store_spec: dict, store_found: dict, locale_found: dict, is_global: bool) -> dict:
    """What this language must have > {slot or group:name : reason}. Conditional slots judged by the store folder"""
    needed = {}
    present_in_store = {slot for slots in store_found.values() for slot in slots}
    for slot_id, slot_spec in store_spec["slots"].items():
        if slot_spec["localized"] == is_global:
            continue
        requirement = slot_spec["requirement"]
        if requirement == "required":
            needed[slot_id] = "required"
        elif requirement == "when_present" and slot_id in present_in_store:
            needed[slot_id] = "present in another locale of this store"
    for group_id, group in store_spec.get("groups", {}).items():
        members = [s for s, spec in store_spec["slots"].items() if spec.get("group") == group_id]
        if is_global or not group.get("required") or not members:
            continue
        if not any(locale_found.get(member) for member in members):
            needed[f"group:{group_id}"] = f"one of: {', '.join(members)}"
    return {key: reason for key, reason in needed.items()
            if key.startswith("group:") or not locale_found.get(key)}
