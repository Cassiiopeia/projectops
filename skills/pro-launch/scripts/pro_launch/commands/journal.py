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
                    "summary": f"{n}건 지움" if n else "그런 제목의 기록이 없다", "next": None})
    text = args.add
    if args.add_file:
        try:
            text = Path(args.add_file).read_text(encoding="utf-8")
        except OSError as e:
            return out({"ok": False, "code": "file_unreadable", "error": str(e),
                        "next": "--add 로 직접 넘기거나 파일 경로를 고친다"})
    if text:
        r = journal.add(path, text, title=args.title, area=args.area or "", site=args.site or "")
        if "error" in r:
            return out({"ok": False, "code": r["error"], "error": r["message"],
                        "next": "내용을 고쳐 다시 부른다"})
        e = r["entry"]
        return out({"ok": True, "code": "ok", "entry": e, "total": r["total"],
                    "summary": f"기록했다: {e['title'] or e['text'][:30]} (총 {r['total']}건)",
                    "next": "다음에 같은 곳을 열면 응답에 journal 로 실려 온다"})
    rows = journal.recent(path, args.limit, area=args.area, site=args.site)
    if not rows:
        return out({"ok": True, "code": "empty", "entries": [],
                    "summary": "적어 둔 작업 기록이 아직 없다",
                    "next": "작업이 끝나면 사용자에게 기록해 둘지 묻고, 동의하면 journal --add 로 적는다"})
    return out({"ok": True, "code": "ok", "entries": rows,
                "summary": f"{len(rows)}건 (최근 순). 참고용이다 — 변경 작업은 사용자 확인을 거친다",
                "next": None})


def configure(p) -> None:
    p.add_argument("--add", default=None, help="적을 내용 (자유 서술. 비밀값 금지)")
    p.add_argument("--add-file", default=None, help="적을 내용이 든 UTF-8 파일 (긴 글·줄바꿈용)")
    p.add_argument("--title", default="", help="한 줄 제목 (지울 때·찾을 때 쓴다)")
    p.add_argument("--area", choices=["ios", "android", "web", "server"], default=None)
    p.add_argument("--site", default=None, help="주소나 서버 이름 일부 (적을 때 붙이고, 찾을 때 거른다)")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--forget", default=None, metavar="TITLE", help="이 제목의 기록을 지운다")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="journal",
            help="했던 작업을 자유롭게 적어 두고 다음에 다시 읽는다 (--add 로 적고, 없으면 최근 것을 보여 준다)",
            run=cmd_journal, configure=configure),
]
