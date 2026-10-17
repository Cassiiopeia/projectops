"""config: design_brief 설정 해석(프로젝트 > 기본 > 이슈 템플릿, 출처 표시) · 저장"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from common.emit import emit

from pro_design_brief.settings import DESTINATIONS


# =========================================================================
# config — design_brief 섹션 (github 아래에 두지 않는다: GitHub 을 안 쓰는 레포도 있다)
# =========================================================================

def _config_path() -> Path:
    return Path.home() / ".projectops" / "config" / "config.json"


def _load_config() -> dict:
    f = _config_path()
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
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


def resolve_config(root: Path, config: dict | None = None) -> dict:
    """우선순위: projects[] 일치 항목 → 섹션 기본값 → 없음(첫 실행 판정)."""
    config = _load_config() if config is None else config
    section = config.get("design_brief") if isinstance(config.get("design_brief"), dict) else {}
    ident = _repo_identity(root)
    match = None
    for p in section.get("projects") or []:
        if not isinstance(p, dict) or not p.get("match"):
            continue
        key = str(p["match"])
        if (ident["slug"] and key.lower() == ident["slug"].lower()) or \
           (key.startswith("/") and Path(key).resolve() == Path(ident["path"])):
            match = p
            break

    resolved, source = {}, {}
    for k in ("destination", "designer", "auto_approve"):
        if match and k in match:
            resolved[k], source[k] = match[k], "project"
        elif k in section:
            resolved[k], source[k] = section[k], "default"
        else:
            resolved[k], source[k] = None, "none"
    if resolved["auto_approve"] is None:
        resolved["auto_approve"] = False   # 안전한 기본값 — 게시 전에 확인받는다

    # 판정 거리 — 정하지 않은 것에 대해 제안만 한다. 저장은 사람이 고른 뒤에.
    suggest = {}
    if resolved["destination"] is None:
        repos = (config.get("github") or {}).get("repos") or []
        known = ident["slug"] and any(
            f"{r.get('owner')}/{r.get('repo')}".lower() == ident["slug"].lower()
            for r in repos if isinstance(r, dict))
        suggest["destination"] = "issue" if (ident["github"] and known) else \
                                 ("issue" if ident["github"] else "html")
        suggest["destination_why"] = ("GitHub 레포이고 등록돼 있다" if known else
                                      "GitHub 레포다 (등록은 안 돼 있다)" if ident["github"] else
                                      "GitHub 레포가 아니다")
    if resolved["designer"] is None:
        suggest["designer_candidates"] = _designer_from_templates(Path(ident["path"]))
    missing = [k for k in ("destination", "designer") if resolved[k] is None]
    return {"repo": ident, "resolved": resolved, "source": source,
            "matched_project": match.get("match") if match else None,
            "suggest": suggest, "missing": missing,
            "config_has_section": bool(section)}


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


def cmd_config(args) -> int:
    root = Path(args.root).resolve()
    if args.action == "show":
        r = resolve_config(root)
        return emit({**r, "config_file": str(_config_path()),
                     "summary": (f"출력 {r['resolved']['destination'] or '미정'} · "
                                 f"디자이너 {r['resolved']['designer'] or '미정'} · "
                                 f"게시 전 확인 {'생략' if r['resolved']['auto_approve'] else '받음'}"),
                     "next": (None if not r["missing"] else
                              f"정해지지 않은 것: {', '.join(r['missing'])} — 사용자에게 한 번에 하나씩 묻고 "
                              "config set 으로 저장한다 (키 이름은 사용자에게 보이지 않는다)")})

    # set — 전체를 읽고 해당 키만 바꿔 쓴다 (config-rules.md §4). 다른 섹션을 날리지 않는다.
    changes = {}
    if args.destination is not None:
        if args.destination not in DESTINATIONS:
            return emit({"ok": False, "code": "bad_destination",
                         "error": f"destination 은 {' · '.join(DESTINATIONS)} 중 하나"})
        changes["destination"] = args.destination
    if args.designer is not None:
        changes["designer"] = args.designer
    if args.auto_approve is not None:
        changes["auto_approve"] = args.auto_approve == "true"
    if not changes:
        return emit({"ok": False, "code": "nothing_to_set",
                     "error": "--destination · --designer · --auto-approve 중 하나는 있어야 합니다"})

    config = _load_config()
    section = config.setdefault("design_brief", {})
    if args.scope == "default":
        section.update(changes)
        target = "default"
    else:
        ident = _repo_identity(root)
        key = ident["slug"] or ident["path"]   # GitHub 이 아니면 경로로 맞춘다
        projects = section.setdefault("projects", [])
        entry = next((p for p in projects if isinstance(p, dict) and
                      str(p.get("match", "")).lower() == key.lower()), None)
        if entry is None:
            entry = {"match": key}
            projects.append(entry)
        entry.update(changes)
        target = key
    f = _config_path()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return emit({"saved": changes, "scope": target, "resolved": resolve_config(root, config)["resolved"],
                 "summary": f"저장했다 ({target})"})
