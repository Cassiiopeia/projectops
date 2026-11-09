"""설정 해석: projects[] 일치 항목 > 섹션 기본값 > 표 기본값 (값마다 출처 표시)
config show · set · options. 쓰기는 presentation 섹션의 그 키만
"""
from __future__ import annotations

from pathlib import Path

from common import config as common_config
from common.emit import emit
from common.preferences import detect_repo

from pro_presentation.options import (CONFIG_SECTION, OPTION_DEFINITIONS, OPTIONS_BY_NAME, default_value,
                                      describe_options, is_valid_option_value, parse_option_value)


def _project_identity(root: Path) -> set[str]:
    owner, repo = detect_repo(str(root))
    return {str(root.resolve())} | ({f"{owner}/{repo}"} if owner and repo else set())


def resolve_config(root: Path) -> dict:
    """옵션별 {value, source} + 잘못 저장된 값(invalid) + 모르는 키(ignored)"""
    data = common_config.load() or {}
    section = data.get(CONFIG_SECTION) if isinstance(data.get(CONFIG_SECTION), dict) else {}
    identity = _project_identity(root)
    project = next((entry for entry in section.get("projects") or []
                    if isinstance(entry, dict) and str(entry.get("match")) in identity), None)
    values, invalid = {}, []
    for definition in OPTION_DEFINITIONS:
        chosen = {"value": default_value(definition), "source": "default"}
        for source_name, source in (("section", section), ("project", project or {})):
            if definition.name in source:
                if is_valid_option_value(definition.name, source[definition.name]):
                    chosen = {"value": source[definition.name], "source": source_name}
                else:
                    invalid.append(f"{source_name}.{definition.name}")
        values[definition.name] = chosen
    known = set(OPTIONS_BY_NAME) | {"projects"}
    ignored = sorted(key for key in section if key not in known)
    return {"values": values, "invalid": invalid, "ignored": ignored,
            "project_match": project.get("match") if project else None}


def option_value(root: Path, name: str):
    return resolve_config(root)["values"][name]["value"]


def cmd_config(args) -> int:
    root = Path(args.root or ".").resolve()
    if args.config_command == "options":
        return emit({"summary": f"{len(OPTION_DEFINITIONS)} options in the '{CONFIG_SECTION}' section",
                     "options": describe_options()})
    if args.config_command == "show":
        resolved = resolve_config(root)
        return emit({"summary": f"Settings for {root}" + (f" (project match {resolved['project_match']})"
                                                          if resolved["project_match"] else ""), **resolved})
    if args.name not in OPTIONS_BY_NAME:
        return emit({"ok": False, "code": "unknown_option", "error": f"No option named {args.name}",
                     "available": sorted(OPTIONS_BY_NAME), "next": "config options"})
    try:
        value = parse_option_value(args.name, args.value)
    except ValueError as error:
        return emit({"ok": False, "code": "invalid_value", "error": str(error), "next": "config options"})
    data = common_config.load() or {}
    section = data.setdefault(CONFIG_SECTION, {})
    if args.project:
        projects = section.setdefault("projects", [])
        entry = next((item for item in projects if isinstance(item, dict) and item.get("match") == args.project), None)
        if entry is None:
            entry = {"match": args.project}
            projects.append(entry)
        entry[args.name] = value
    else:
        section[args.name] = value
    path = common_config.save(data)
    return emit({"summary": f"Saved {args.name} = {value}" + (f" for {args.project}" if args.project else ""),
                 "config_file": str(path), "name": args.name, "value": value})
