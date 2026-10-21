"""`journal` — 했던 작업을 자유롭게 적어 두고, 다음에 같은 곳에서 다시 읽는다."""
from __future__ import annotations

from pathlib import Path

import journal

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root
from pro_launch.runtime.output import out


def cmd_journal(args) -> int:
    path = journal.store_path(project_root(args))
    if args.forget:
        n = journal.forget(path, args.forget)
        return out({"ok": True, "code": "ok" if n else "not_found", "removed": n,
                    "summary": f"Removed {n} entries" if n else "No entry with that title", "next": None})
    text = args.add
    if args.add_file:
        try:
            text = Path(args.add_file).read_text(encoding="utf-8")
        except OSError as e:
            return out({"ok": False, "code": "file_unreadable", "error": str(e),
                        "next": "Pass the text with --add or fix the file path"})
    if text:
        r = journal.add(path, text, title=args.title, area=args.area or "", site=args.site or "")
        if "error" in r:
            return out({"ok": False, "code": r["error"], "error": r["message"],
                        "next": "Fix the text and call again"})
        e = r["entry"]
        return out({"ok": True, "code": "ok", "entry": e, "total": r["total"],
                    "summary": f"Recorded: {e['title'] or e['text'][:30]} ({r['total']} total)",
                    "next": "Next time the same place is opened, it comes back in the response as journal"})
    rows = journal.recent(path, args.limit, area=args.area, site=args.site)
    if not rows:
        return out({"ok": True, "code": "empty", "entries": [],
                    "summary": "No work journal entries yet",
                    "next": "When the work is done, ask the user whether to record it; if they agree, write it with journal --add"})
    return out({"ok": True, "code": "ok", "entries": rows,
                "summary": f"{len(rows)} entries (newest first). For reference only — changes still need user confirmation",
                "next": None})


def configure(p) -> None:
    p.add_argument("--add", default=None, help="Text to record (free form, no secrets)")
    p.add_argument("--add-file", default=None, help="UTF-8 file with the text to record (for long text or line breaks)")
    p.add_argument("--title", default="", help="One-line title (used to remove or find it)")
    p.add_argument("--area", choices=["ios", "android", "web", "server"], default=None)
    p.add_argument("--site", default=None, help="Part of a url or server name (attached when recording, filters when reading)")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--forget", default=None, metavar="TITLE", help="Remove the entry with this title")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="journal",
            help="Record past work in free form and read it back later (write with --add; without it, shows recent entries)",
            run=cmd_journal, configure=configure),
]
