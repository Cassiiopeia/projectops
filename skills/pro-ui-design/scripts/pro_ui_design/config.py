"""config: resolve ui-design settings (with source), save, show option table
Resolution order: project > section defaults > legacy design_brief (project > defaults) > option table defaults
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from common.config import config_path, load_with_status
from common.emit import emit

from pro_ui_design.options import (CONFIG_SECTION, LEGACY_CONFIG_SECTION, OPTION_DEFINITIONS, OPTIONS_BY_NAME,
                                   default_value, describe_options, is_valid_option_value, parse_option_value)
from pro_ui_design.session import write_json_atomically
from pro_ui_design.settings import DESTINATIONS

# Structural keys that are not options: excluded from unknown-key check
STRUCTURAL_SECTION_KEYS = {"projects"}
STRUCTURAL_PROJECT_KEYS = {"match"}
# Options to ask a person about on first run
ASK_ON_FIRST_RUN = ("destination", "designer")


def _load_config() -> dict:
    data, _ = load_with_status()
    return data if isinstance(data, dict) else {}


def _is_config_unreadable() -> bool:
    data, status = load_with_status()
    return status == "unreadable" or (data is not None and not isinstance(data, dict))


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _repo_identity(root: Path) -> dict:
    """{slug: owner/repo or None, path: absolute repo path, github: bool}."""
    top = _git(root, "rev-parse", "--show-toplevel") or str(root)
    url = _git(root, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url) if url else None
    return {"slug": f"{m.group(1)}/{m.group(2)}" if m else None,
            "path": str(Path(top).resolve()), "github": bool(m)}


def _read_section(config: dict, name: str) -> dict:
    section = config.get(name)
    return section if isinstance(section, dict) else {}


def _find_matching_project(section: dict, identity: dict) -> dict | None:
    """This repo's entry in projects[]: owner/repo or absolute path"""
    for project in section.get("projects") or []:
        if not isinstance(project, dict) or not project.get("match"):
            continue
        key = str(project["match"])
        if identity["slug"] and key.lower() == identity["slug"].lower():
            return project
        if Path(key).is_absolute() and Path(key).resolve() == Path(identity["path"]):
            return project
    return None


def _find_unknown_keys(section: dict) -> list[str]:
    """Unknown keys: report, never delete (keeps settings from other versions)"""
    unknown = {key for key in section if key not in OPTIONS_BY_NAME and key not in STRUCTURAL_SECTION_KEYS}
    for project in section.get("projects") or []:
        if isinstance(project, dict):
            unknown |= {key for key in project if key not in OPTIONS_BY_NAME and key not in STRUCTURAL_PROJECT_KEYS}
    return sorted(unknown)


def resolve_config(root: Path, config: dict | None = None) -> dict:
    """Resolve each option's value and source (project, default, legacy, builtin) + first-run suggestions"""
    config = _load_config() if config is None else config
    section = _read_section(config, CONFIG_SECTION)
    legacy_section = _read_section(config, LEGACY_CONFIG_SECTION)
    identity = _repo_identity(root)
    project = _find_matching_project(section, identity)
    legacy_project = _find_matching_project(legacy_section, identity)
    layers = [(project, "project"), (section, "default"), (legacy_project, "legacy"), (legacy_section, "legacy")]

    resolved, source, invalid = {}, {}, []
    for definition in OPTION_DEFINITIONS:
        name = definition.name
        resolved[name], source[name] = default_value(definition), "builtin"
        for layer, layer_source in layers:
            if not layer or name not in layer:
                continue
            if is_valid_option_value(name, layer[name]):
                resolved[name], source[name] = layer[name], layer_source
                break
            invalid.append(name)

    matched = project or legacy_project
    return {"repo": identity, "resolved": resolved, "source": source, "invalid": sorted(set(invalid)),
            "ignored": _find_unknown_keys(section), "matched_project": matched.get("match") if matched else None,
            "suggest": _build_suggestions(config, identity, resolved),
            "missing": [name for name in ASK_ON_FIRST_RUN if resolved[name] is None],
            "config_has_section": bool(section or legacy_section)}


def _build_suggestions(config: dict, identity: dict, resolved: dict) -> dict:
    """Suggestions for unset values only. Saved after a person picks"""
    suggest = {}
    if resolved["destination"] is None:
        repos = (config.get("github") or {}).get("repos") or []
        known = identity["slug"] and any(
            f"{r.get('owner')}/{r.get('repo')}".lower() == identity["slug"].lower()
            for r in repos if isinstance(r, dict))
        suggest["destination"] = "issue" if identity["github"] else "html"
        suggest["destination_why"] = ("GitHub repo, registered in config" if known else
                                      "GitHub repo (not registered in config)" if identity["github"] else
                                      "not a GitHub repo")
    if resolved["designer"] is None:
        suggest["designer_candidates"] = _designer_from_templates(Path(identity["path"]))
    return suggest


_PLACEHOLDERS = {"이름", "담당자", "디자이너", "name", "designer", "todo", "-", "tbd", "없음"}


def _designer_from_templates(root: Path) -> list[str]:
    """Assignee candidates from the `디자인:` line in issue templates. The agent checks recent design issue assignees via pro-github."""
    found: list[str] = []
    d = root / ".github" / "ISSUE_TEMPLATE"
    if not d.is_dir():
        return found
    for f in sorted(d.glob("*")):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"디자인\**\s*[:：][ \t]*@?([^\s,*]+)", text):
            v = m.group(1).strip()
            # Do not read template placeholders (`디자인: 이름`, etc.) as assignees — hit in practice
            if v and v not in found and not v.startswith(("{", "[", "<")) \
                    and v.lower() not in _PLACEHOLDERS:
                found.append(v)
    return found


def cmd_config(args) -> int:
    if args.action == "options":
        return emit({"options": describe_options(), "section": CONFIG_SECTION,
                     "summary": f"{len(OPTION_DEFINITIONS)} options"})
    root = Path(args.root).resolve()
    if args.action == "show":
        return _show_config(root)
    return _save_config(args, root)


def _show_config(root: Path) -> int:
    r = resolve_config(root)
    return emit({**r, "config_file": str(config_path()),
                 "summary": (f"Output {r['resolved']['destination'] or 'not set'} · "
                             f"designer {r['resolved']['designer'] or 'not set'} · "
                             f"confirm before posting {'skipped' if r['resolved']['auto_approve'] else 'yes'}"),
                 "next": (None if not r["missing"] else
                          f"Not set yet: {', '.join(r['missing'])}. Ask the user one at a time and "
                          "save with config set (do not show key names to the user)")})


def _collect_changes(args) -> tuple[dict, dict | None]:
    """Arguments > values to change. On failure (empty, error response)"""
    changes = {}
    if args.destination is not None:
        if args.destination not in DESTINATIONS:
            return {}, {"ok": False, "code": "bad_destination",
                        "error": f"destination must be one of {' · '.join(DESTINATIONS)}"}
        changes["destination"] = args.destination
    if args.designer is not None:
        changes["designer"] = args.designer
    if args.auto_approve is not None:
        changes["auto_approve"] = args.auto_approve == "true"
    if args.key is not None:
        if args.key not in OPTIONS_BY_NAME:
            return {}, {"ok": False, "code": "unknown_option", "error": f"Unknown option: {args.key}",
                        "next": "ui_design_cli.py config options"}
        try:
            changes[args.key] = parse_option_value(args.key, args.value or "")
        except ValueError as error:
            return {}, {"ok": False, "code": "bad_option_value", "error": str(error)}
    if not changes:
        return {}, {"ok": False, "code": "nothing_to_set",
                    "error": "Pass --destination, --designer, --auto-approve, or --key with --value"}
    return changes, None


def _save_config(args, root: Path) -> int:
    """Read everything, change only the given keys (config-rules.md §4), save to the new section only"""
    changes, failure = _collect_changes(args)
    if failure:
        return emit(failure)
    if _is_config_unreadable():   # Overwriting a broken file would wipe other settings like the PAT
        return emit({"ok": False, "code": "config_unreadable", "error": f"Could not read {config_path()}",
                     "next": "Ask the user to fix that file. It was not changed"})
    config = _load_config()
    section = config.setdefault(CONFIG_SECTION, {})
    if args.scope == "default":
        section.update(changes)
        target = "default"
    else:
        identity = _repo_identity(root)
        key = identity["slug"] or identity["path"]   # Match by path when not on GitHub
        projects = section.setdefault("projects", [])
        entry = next((p for p in projects if isinstance(p, dict) and
                      str(p.get("match", "")).lower() == key.lower()), None)
        if entry is None:
            entry = {"match": key}
            projects.append(entry)
        entry.update(changes)
        target = key
    write_json_atomically(config_path(), config)
    return emit({"saved": changes, "scope": target, "resolved": resolve_config(root, config)["resolved"],
                 "summary": f"Saved ({target})"})
