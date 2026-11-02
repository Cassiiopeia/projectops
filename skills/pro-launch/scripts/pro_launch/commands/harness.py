"""`harness` — 반복하는 사이트·작업의 안내서 폴더를 찾고·보고·맞추고·만든다 (projectops#1023).

하네스는 폴더 하나다(`harness_store`). 새 사이트·작업을 더할 때 코드를 고치지 않는다 — `harness new` 나 손으로 폴더를 만든다.
읽기는 맞는 주소·호스트·앱·창으로 향하는 명령의 응답에 `harness` 로 자동으로 실리고, 이 명령은 전체를 볼 때 쓴다.
앱(패키지명·번들 ID)·창(제목·프로그램 이름) 맞추기는 projectops#1024.
"""
from __future__ import annotations

from pathlib import Path

import harness_store
import knowledge

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root
from pro_launch.runtime.output import out

HARNESS_ACTIONS = ("list", "show", "match", "new")
# show 가 돌려주는 README 상한 — 넘으면 잘라서 주고 경로로 Read 하게 한다
SHOW_MAX_CHARS = 12000


def _entry_brief(entry: dict) -> dict:
    return {k: entry.get(k) for k in ("name", "scope", "description", "path", "readme", "match", "areas",
                                      "has_meta", "files", "meta_error", "shadows", "matched_by") if entry.get(k) is not None}


def _list(args) -> int:
    rows = harness_store.list_all(project_root(args))
    if not rows:
        return out({"ok": True, "code": "empty", "harnesses": [], "dirs": _dirs(args),
                    "summary": "No harness yet",
                    "next": "When a site workflow repeats, create one: harness new <name> --description \"...\" --url \"https://host/*\""})
    return out({"ok": True, "code": "ok", "harnesses": [_entry_brief(e) for e in rows], "dirs": _dirs(args),
                "summary": f"{len(rows)} harness(es)", "next": "harness show <name>  # read the guide"})


def _dirs(args) -> dict:
    return {scope: str(d) for scope, d in harness_store.scope_dirs(project_root(args))}


def _show(args) -> int:
    if not args.name:
        return out({"ok": False, "code": "name_required", "error": "A harness name is required",
                    "next": "harness list  # pick a name"})
    entry = harness_store.find(project_root(args), args.name)
    if entry is None:
        return out({"ok": False, "code": "not_found", "error": f"No harness named {args.name}",
                    "next": "harness list"})
    payload = {"ok": True, "code": "ok", "entry": _entry_brief(entry), "summary": entry["description"] or entry["name"]}
    if entry["readme"]:
        text = Path(entry["readme"]).read_text(encoding="utf-8-sig", errors="replace")
        payload["readme_text"] = text[:SHOW_MAX_CHARS]
        payload["truncated"] = len(text) > SHOW_MAX_CHARS
        payload["next"] = ("Follow the loop and stop at the human-check points. When the screen or steps changed, "
                           f"update {entry['readme']}")
    else:
        payload["code"] = "no_readme"
        payload["next"] = f"Write the guide at {entry['path']}/README.md (goal · loop · human checks · when stuck)"
    return out(payload)


def _match(args) -> int:
    if not args.url and not args.host and not args.app and not args.window:
        return out({"ok": False, "code": "target_required", "error": "Give --url, --host, --app or --window",
                    "next": "harness match --url https://host:port/path  # or --app com.example.app · --window \"Setup\""})
    rows = harness_store.matching(project_root(args), url=args.url, host=args.host, area=args.area,
                                  app=args.app, window=args.window)
    if not rows:
        return out({"ok": True, "code": "empty", "matches": [],
                    "summary": "No harness matches", "next": None})
    return out({"ok": True, "code": "ok",
                "matches": [{**_entry_brief(e), "excerpt": harness_store.excerpt(e["readme"])} for e in rows],
                "summary": f"{len(rows)} match(es): {', '.join(e['name'] for e in rows)}",
                "next": f"harness show {rows[0]['name']}"})


def _new(args) -> int:
    if not args.name:
        return out({"ok": False, "code": "name_required", "error": "A harness name is required",
                    "next": "harness new <name> --description \"...\" --url \"https://host/*\""})
    result = harness_store.create(project_root(args), args.name, description=args.description or "",
                                  hosts=args.host_list, urls=args.url_list, areas=args.area_list,
                                  scope=args.scope, lang=args.lang, apps=args.app_list, windows=args.window_list)
    if "error" in result:
        failure = {"ok": False, "code": result["error"], "error": result["message"],
                   "next": "Fix the value and call again"}
        if result.get("entry"):
            failure["entry"] = _entry_brief(result["entry"])
            failure["next"] = f"harness show {args.name}  # edit that folder instead"
        return out(failure)
    entry = result["entry"]
    no_match = not any(entry["match"].values())
    return out({"ok": True, "code": "ok", "entry": _entry_brief(entry), "language": result["language"],
                "summary": f"Created {entry['path']}" + (" (no --host/--url/--app/--window: listed only, never auto-shown)"
                                                         if no_match else ""),
                "next": (f"Fill in {entry['readme']} (goal · loop · human checks · when stuck) and put helper scripts beside it. "
                         "Never write secrets there — accounts go in cred")})


_HANDLERS = {"list": _list, "show": _show, "match": _match, "new": _new}


def cmd_harness(args) -> int:
    # match 는 --url · --host · --app · --window · --area 를 한 값(마지막 값)으로 쓴다. new 는 목록 그대로
    args.url = (args.url_list or [None])[-1]
    args.host = (args.host_list or [None])[-1]
    args.app = (args.app_list or [None])[-1]
    args.window = (args.window_list or [None])[-1]
    args.area = (args.area_list or [None])[-1]
    return _HANDLERS[args.action](args)


def configure(p) -> None:
    p.add_argument("action", choices=list(HARNESS_ACTIONS))
    # 위치 인자는 하나 (#622): show · new 의 이름
    p.add_argument("name", nargs="?", default=None, help="show · new: harness name (folder name)")
    p.add_argument("--description", default=None, help="new: one line on what this harness is for")
    # match 는 한 값, new 는 여러 번 줄 수 있다
    p.add_argument("--url", dest="url_list", action="append", default=None,
                   help="match: the URL to test · new: URL pattern to auto-surface on (* wildcard, repeatable)")
    p.add_argument("--host", dest="host_list", action="append", default=None,
                   help="match: the host to test · new: host to auto-surface on (host or host:port, * wildcard, repeatable)")
    p.add_argument("--app", dest="app_list", action="append", default=None,
                   help="match: the package name / bundle ID to test · new: app id pattern to auto-surface on "
                        "(Android package · iOS bundle ID, * wildcard, repeatable)")
    p.add_argument("--window", dest="window_list", action="append", default=None,
                   help="match: the window title or program name to test · new: desktop window title / program "
                        "pattern to auto-surface on (* wildcard, repeatable)")
    # app 명령의 영역 app 은 ios · android 와 통한다 (harness_store.area_applies)
    p.add_argument("--area", dest="area_list", action="append", choices=[*knowledge.AREAS, harness_store.APP_AREA],
                   default=None,
                   help="match: only harnesses for this area · new: areas it applies to (repeatable; none = all)")
    p.add_argument("--scope", choices=list(harness_store.SCOPES), default="machine",
                   help="new: machine (whole computer, default) or repo (this repo only)")
    p.add_argument("--lang", choices=list(harness_store.LANGUAGES), default=None,
                   help="new: README skeleton language (default: repo language > this computer's locale > en)")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="harness",
            help="Guides for repeated site, app or desktop work (README + optional helper scripts): list · show · match · new",
            run=cmd_harness, configure=configure),
]
