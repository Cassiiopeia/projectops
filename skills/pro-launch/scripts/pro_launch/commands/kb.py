"""`kb` — 공식 트러블슈팅 지식 찾기·보기·목록, 내 기억에서 공식 항목 초안 뽑기 (#889).

공식 지식(skills/pro-launch/troubleshooting/)은 관리자가 PR 로 넣는다. 이 명령은 읽기만 한다 —
`propose` 도 파일에 쓰지 않고 초안을 응답으로만 준다. 사람이 다듬어 이슈나 PR 로 올린다.
"""
from __future__ import annotations

import re

from common import memory, troubleshoot
from common.access import find_secrets
from common.state import repo_unknown

import knowledge

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root
from pro_launch.runtime.output import SKILL_DIR, out

KB_ACTIONS = ("search", "show", "list", "propose")
DEFAULT_SEARCH_LIMIT = 5
# propose 대상: 여러 번 먹혔고 실패가 성공보다 적은 기억
PROPOSE_MIN_OK = 3
PROPOSE_KEYWORD_COUNT = 5
# 초안에서 사람이 채워야 하는 칸
PROPOSE_TODO_FIELDS = ["title", "match.codes", "symptom", "cause", "refs"]


def _search(args) -> int:
    text = args.query or ""
    if not text.strip() and not args.code:
        return out({"ok": False, "code": "query_required", "error": "Give a text to search for or --code",
                    "next": "kb search \"<error text>\" --code <failure code>"})
    rows = troubleshoot.find_known_fixes(SKILL_DIR, args.code, text, limit=args.limit)
    if not rows:
        return out({"ok": True, "code": "empty", "matches": [],
                    "summary": "No matching official entry", "next": "kb list  # all entries"})
    return out({"ok": True, "code": "ok", "matches": rows, "summary": f"{len(rows)} match(es)",
                "next": f"kb show {rows[0]['id']}  # full symptom, cause and fix"})


def _show(args) -> int:
    if not args.query:
        return out({"ok": False, "code": "id_required", "error": "An entry id is required",
                    "next": "kb list  # pick an id"})
    entry = troubleshoot.load_entry(SKILL_DIR, args.query)
    if entry is None:
        return out({"ok": False, "code": "not_found", "error": f"No such entry: {args.query}",
                    "next": "kb search \"<error text>\"  # or kb list"})
    return out({"ok": True, "code": "ok", "entry": entry, "summary": entry.get("title"),
                "next": "Try the fix steps in order"})


def _list(args) -> int:
    rows = troubleshoot.list_entries(SKILL_DIR, args.area)
    return out({"ok": True, "code": "ok" if rows else "empty", "entries": rows,
                "summary": f"{len(rows)} entries", "next": "kb show <id>" if rows else None})


def _knowledge_paths(args) -> dict:
    """사용자 기억 파일 — 이 컴퓨터 범위 + (레포를 알면) 이 레포 범위."""
    root = project_root(args)
    paths = {"machine": knowledge.store_path("machine", root)}
    if not repo_unknown(root):
        paths["repo"] = knowledge.store_path("repo", root)
    return paths


def _draft(entry: dict) -> dict:
    """사용자 기억 하나 > 공식 항목 초안 (사람이 채울 칸은 비워 둔다)."""
    # 기억 key(ios.tap) > 항목 id(ios-tap)
    entry_id = re.sub(r"[^a-z0-9]+", "-", entry["key"].lower()).strip("-")
    keywords = sorted(memory.words(entry["how"]))[:PROPOSE_KEYWORD_COUNT]
    return {"id": entry_id, "area": entry["area"], "title": "", "match": {"codes": [], "keywords": keywords},
            "symptom": "", "cause": "", "fix": [entry["how"]], "refs": [],
            "verified_at": entry.get("last_seen") or memory.today()}


def _propose(args) -> int:
    wanted_key = knowledge.norm_key(args.key) if args.key else None
    drafts, skipped = [], []
    for scope, path in _knowledge_paths(args).items():
        for entry in knowledge.load(path):
            # 대상 고르기 (key·area 필터, 성적 기준)
            if wanted_key and entry["key"] != wanted_key:
                continue
            if args.area and entry["area"] != args.area:
                continue
            if entry["ok"] < PROPOSE_MIN_OK or entry["fail"] >= entry["ok"]:
                continue
            # 비밀값 거름 — 초안은 이슈·PR 로 공개된다
            secrets = find_secrets(f"{entry['key']} {entry['how']}")
            if secrets:
                skipped.append({"key": entry["key"], "scope": scope, "reason": "secret_detected"})
                continue
            draft = _draft(entry)
            drafts.append({"scope": scope, "ok": entry["ok"], "fail": entry["fail"],
                           "path": f"troubleshooting/{draft['area']}/{draft['id']}.json",
                           "draft": draft, "todo": PROPOSE_TODO_FIELDS})
    if not drafts:
        return out({"ok": True, "code": "empty", "drafts": [], "skipped": skipped or None,
                    "summary": f"No memory worth proposing as official (ok>={PROPOSE_MIN_OK}, fail<ok)",
                    "next": None})
    return out({"ok": True, "code": "ok", "drafts": drafts, "skipped": skipped or None,
                "summary": f"{len(drafts)} draft(s) — nothing written to disk",
                "next": ("Fill the todo fields, confirm with the user, then submit skills/pro-launch/<path> as an issue or PR "
                         "(a maintainer reviews it. Writing rules: skills/references/memory-principles.md §6)")})


_HANDLERS = {"search": _search, "show": _show, "list": _list, "propose": _propose}


def cmd_kb(args) -> int:
    return _HANDLERS[args.action](args)


def configure_kb(p) -> None:
    p.add_argument("action", choices=list(KB_ACTIONS))
    # 위치 인자는 하나 (#622): search 는 찾을 문구, show 는 항목 id
    p.add_argument("query", nargs="?", default=None, help="search: error text · show: entry id")
    p.add_argument("--code", default=None, help="search: the code of the failed response")
    p.add_argument("--area", choices=list(troubleshoot.AREAS), default=None, help="list·propose: area")
    p.add_argument("--key", default=None, help="propose: only this memory key")
    p.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT, help="search: maximum matches")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="kb", help="Search, show and list official troubleshooting; draft official entries from your memory",
            run=cmd_kb, configure=configure_kb),
]
