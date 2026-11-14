"""`kb` — search, show and list official troubleshooting knowledge; draft official entries from my memory (#889).

Official knowledge (skills/pro-launch/troubleshooting/) is added by maintainers via PR. This command only reads —
even `propose` writes no file and returns the draft in the response only. A person polishes it into an issue or PR.
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
# propose targets: memories that worked several times and failed less than they succeeded
PROPOSE_MIN_OK = 3
PROPOSE_KEYWORD_COUNT = 5
# Fields in the draft a person must fill in
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
    """User memory files — this computer's scope + (if the repo is known) this repo's scope."""
    root = project_root(args)
    paths = {"machine": knowledge.store_path("machine", root)}
    if not repo_unknown(root):
        paths["repo"] = knowledge.store_path("repo", root)
    return paths


def _draft(entry: dict) -> dict:
    """One user memory > official entry draft (fields for a person are left empty)."""
    # memory key (ios.tap) > entry id (ios-tap)
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
            # Pick targets (key·area filters, track record)
            if wanted_key and entry["key"] != wanted_key:
                continue
            if args.area and entry["area"] != args.area:
                continue
            if entry["ok"] < PROPOSE_MIN_OK or entry["fail"] >= entry["ok"]:
                continue
            # Filter out secrets — drafts are published as issues/PRs
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
    # One positional argument (#622): search phrase for search, entry id for show
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
