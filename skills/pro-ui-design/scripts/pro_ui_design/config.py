"""config: ui-design 설정 해석(출처 표시) · 저장 · 옵션 표 조회
해석 순서: 프로젝트 > 섹션 기본값 > 옛 design_brief(프로젝트 > 기본값) > 옵션 표 기본값
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from common.config import config_path
from common.emit import emit

from pro_ui_design.options import (CONFIG_SECTION, LEGACY_CONFIG_SECTION, OPTION_DEFINITIONS, OPTIONS_BY_NAME,
                                   default_value, describe_options, is_valid_option_value, parse_option_value)
from pro_ui_design.settings import DESTINATIONS

# 옵션이 아닌 구조 키: 모르는 키 판정에서 제외
STRUCTURAL_SECTION_KEYS = {"projects"}
STRUCTURAL_PROJECT_KEYS = {"match"}
# 첫 실행에 사람에게 물어야 하는 옵션
ASK_ON_FIRST_RUN = ("destination", "designer")


# =========================================================================
# 읽기
# =========================================================================

def _load_config() -> dict:
    config_file = config_path()
    if not config_file.is_file():
        return {}
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _repo_identity(root: Path) -> dict:
    """{slug: owner/repo 또는 None, path: 레포 절대경로, github: bool}."""
    top = _git(root, "rev-parse", "--show-toplevel") or str(root)
    url = _git(root, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url) if url else None
    return {"slug": f"{m.group(1)}/{m.group(2)}" if m else None,
            "path": str(Path(top).resolve()), "github": bool(m)}


def _read_section(config: dict, name: str) -> dict:
    section = config.get(name)
    return section if isinstance(section, dict) else {}


def _find_matching_project(section: dict, identity: dict) -> dict | None:
    """projects[] 중 이 레포 항목: owner/repo 또는 절대경로"""
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
    """모르는 키: 지우지 않고 알리기만 (다른 버전의 설정 보존)"""
    unknown = {key for key in section if key not in OPTIONS_BY_NAME and key not in STRUCTURAL_SECTION_KEYS}
    for project in section.get("projects") or []:
        if isinstance(project, dict):
            unknown |= {key for key in project if key not in OPTIONS_BY_NAME and key not in STRUCTURAL_PROJECT_KEYS}
    return sorted(unknown)


def resolve_config(root: Path, config: dict | None = None) -> dict:
    """옵션별 값과 출처(project, default, legacy, builtin) 해석 + 첫 실행 제안"""
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
    """정하지 않은 값의 제안만. 저장은 사람이 고른 뒤"""
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
    """이슈 템플릿의 `디자인:` 줄에서 담당자 후보. 최근 디자인 이슈 담당자는 agent 가 pro-github 로 본다."""
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
            # 템플릿 자리표시(`디자인: 이름` 등)를 담당자로 읽지 않는다 — 실측으로 걸렸다
            if v and v not in found and not v.startswith(("{", "[", "<")) \
                    and v.lower() not in _PLACEHOLDERS:
                found.append(v)
    return found


# =========================================================================
# 명령
# =========================================================================

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
    """인자 > 바꿀 값. 실패면 (빈 값, 오류 응답)"""
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
    """전체를 읽고 해당 키만 변경 (config-rules.md §4), 저장은 새 섹션에만"""
    changes, failure = _collect_changes(args)
    if failure:
        return emit(failure)
    config = _load_config()
    section = config.setdefault(CONFIG_SECTION, {})
    if args.scope == "default":
        section.update(changes)
        target = "default"
    else:
        identity = _repo_identity(root)
        key = identity["slug"] or identity["path"]   # GitHub 이 아니면 경로로 맞춘다
        projects = section.setdefault("projects", [])
        entry = next((p for p in projects if isinstance(p, dict) and
                      str(p.get("match", "")).lower() == key.lower()), None)
        if entry is None:
            entry = {"match": key}
            projects.append(entry)
        entry.update(changes)
        target = key
    config_file = config_path()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return emit({"saved": changes, "scope": target, "resolved": resolve_config(root, config)["resolved"],
                 "summary": f"Saved ({target})"})
