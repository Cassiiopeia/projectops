"""`recall` · `learn` · `forget` — 이 컴퓨터에서 먹힌 조작 방식을 기억한다 (tidy 는 commands/tidy.py)."""
from __future__ import annotations


from pathlib import Path

from common.state import repo_unknown

import knowledge
import knowledge_stale

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root
from pro_launch.runtime.output import out


def _knowledge_paths(args) -> dict:
    scope = getattr(args, "scope", "both")
    root = project_root(args)
    want = ("repo", "machine") if scope == "both" else (scope,)
    if repo_unknown(root):
        # 어느 레포인지 모르면 레포 범위를 만들지 않는다 — 'scripts' 같은 가짜 레포가 생긴다
        want = ("machine",)
    return {sc: knowledge.store_path(sc, root) for sc in want}


def _learn_scope(args) -> str:
    return "machine" if args.scope == "repo" and repo_unknown(project_root(args)) else args.scope


def cmd_recall(args) -> int:
    rows = knowledge.recall(_knowledge_paths(args), args.area, args.limit, match=args.match)
    if not rows:
        return out({"ok": True, "code": "empty", "entries": [],
                    "summary": (f"No memory contains '{args.match}'" if args.match
                                else "No methods recorded on this computer yet"),
                    "next": "When done, record what worked with launch_cli.py learn"})
    return out({"ok": True, "code": "ok", "entries": rows,
                "summary": f"{len(rows)} entries (verify:true means check once before use"
                           + (", detail_path is a longer background note — read it if needed)" if any("detail_path" in r for r in rows)
                              else ")"),
                "next": "Report whether it worked with learn --result ok|fail"})


def _supersede(args) -> int:
    """learn --supersede KEY --by X: 항목을 지우지 않고 X(kb:<id> · feature:<명령>)로 대체됐다고 표시."""
    if not args.by:
        return out({"ok": False, "code": "by_required", "error": "--supersede requires --by",
                    "next": "learn --supersede <key> --by kb:<id>  # or feature:<command>"})
    path = knowledge.store_path(args.scope, project_root(args))
    marked = knowledge_stale.mark_superseded(path, args.supersede, args.by, area=args.area)
    return out({"ok": bool(marked), "code": "ok" if marked else "not_found", "marked": marked,
                "summary": f"Marked {args.supersede} as superseded by {args.by}" if marked else "No such entry",
                "next": "recall  # superseded entries go last and are not included in responses" if marked else None})


def cmd_learn(args) -> int:
    args.scope = _learn_scope(args)
    if args.supersede:
        return _supersede(args)
    missing = [name for name in ("area", "key", "how", "result") if not getattr(args, name)]
    if missing:
        return out({"ok": False, "code": "bad_args",
                    "error": f"learn requires --{', --'.join(missing)}",
                    "next": "learn --area <area> --key <key> --how <method> --result ok|fail"})
    repo_path = None if args.scope == "machine" else knowledge.store_path("repo", project_root(args))
    detail, err = _read_detail(args)
    if err:
        return out(err)
    r = knowledge.learn_smart(repo_path, args.area, args.key, args.how, args.result, args.scope,
                              detail=detail)
    if "error" in r:
        failure = {"ok": False, "code": r["error"], "error": r["message"],
                   "next": _learn_retry_hint(r)}
        # 무엇이 걸렸는지 그대로 싣는다 — too_long 은 길이·상한, secret_detected 는 가린 구간
        failure.update({k: r[k] for k in ("length", "limit", "matched_span") if k in r})
        return out(failure)
    e = r["entry"]
    note = (f" — merged with {r['promoted_from']} matching entries from other repos and promoted to machine scope"
            if r.get("promoted_from") else "")
    rel = r.get("related") or []
    return out({"ok": True, "code": "ok", "entry": e, "scope": r["scope"],
                "promoted_from": r.get("promoted_from", 0), "related": rel or None,
                "summary": f"{e['key']} ok={e['ok']} fail={e['fail']} ({r['scope']}){note}",
                # 비슷한 기억이 있으면 같은 지식인지 agent 가 판단한다 — 도구가 애매한 것을 멋대로 합치지 않는다
                "next": (f"If a related entry is the same knowledge, run forget --key <the key just saved>, then "
                         f"learn --scope machine --key <that key> to merge" if rel else None)})


def _read_detail(args) -> tuple[str | None, dict | None]:
    """--detail 글 또는 --detail-file 파일 내용 > (본문, 실패 결과)."""
    if not getattr(args, "detail_file", None):
        return args.detail, None
    try:
        return Path(args.detail_file).read_text(encoding="utf-8"), None
    except OSError as e:
        return None, {"ok": False, "code": "file_unreadable", "error": str(e),
                      "next": "Pass it directly with --detail or fix the file path"}


def _learn_retry_hint(result: dict) -> str:
    """거절 사유별 다음 행동."""
    if result["error"] == "too_long":
        return ("Keep how to a one-line conclusion; pass why it was blocked and how it was solved "
                "with --detail \"<long text>\" (or --detail-file <file>)")
    if result["error"] == "secret_detected":
        return "Remove the value part of matched_span or replace it with something like <password>, then retry (keep accounts in cred)"
    return "Fix the content and retry"


def cmd_forget(args) -> int:
    args.scope = _learn_scope(args)
    path = knowledge.store_path(args.scope, project_root(args))
    if args.by:
        # 지우지 않고 대체 표시만 (--by kb:<id> · feature:<명령>)
        n = knowledge_stale.mark_superseded(path, args.key, args.by, area=args.area)
        return out({"ok": True, "code": "ok" if n else "not_found", "marked": n,
                    "summary": f"Marked {n} as superseded" if n else "No such entry", "next": None})
    n = knowledge.forget(path, args.key, args.area)
    return out({"ok": True, "code": "ok" if n else "not_found", "removed": n,
                "summary": f"Removed {n}" if n else "No such entry", "next": None})


def configure_recall(p) -> None:
    # --platform 은 --area 의 별칭 (추측으로 많이 쓰는 이름, #931)
    p.add_argument("--area", "--platform", dest="area", choices=list(knowledge.AREAS), default=None)
    p.add_argument("--limit", type=int, default=knowledge.DEFAULT_LIMIT)
    p.add_argument("--match", default=None, help="only entries whose key·method·note contain this word (e.g. swipe)")
    p.add_argument("--scope", choices=["both", "repo", "machine"], default="both")
    p.add_argument("--root", default=".")


def configure_learn(p) -> None:
    # area·key·how·result 는 --supersede 일 때만 생략한다 — cmd_learn 이 확인
    p.add_argument("--area", choices=list(knowledge.AREAS), default=None)
    p.add_argument("--key", default=None, help="one-line name (e.g. ios.tap)")
    p.add_argument("--how", default=None, help=f"method (up to {knowledge.MAX_HOW} chars, no secrets)")
    p.add_argument("--result", choices=["ok", "fail"], default=None)
    p.add_argument("--supersede", default=None, metavar="KEY", help="mark this key as superseded by --by instead of deleting it")
    p.add_argument("--by", default=None, help="what replaced it: kb:<id> · feature:<command> (for --supersede · forget)")
    p.add_argument("--detail", default=None,
                   help=f"longer background·reason (up to {knowledge.MAX_DETAIL} chars) — kept in notes/<key>.md, recall returns the path")
    p.add_argument("--detail-file", default=None, help="UTF-8 file instead of --detail (for multi-line text)")
    p.add_argument("--scope", choices=list(knowledge.SCOPES), default="repo")
    p.add_argument("--root", default=".")


def configure_forget(p) -> None:
    p.add_argument("--key", required=True)
    p.add_argument("--by", default=None, help="only mark as superseded by kb:<id> · feature:<command>, without deleting")
    p.add_argument("--area", choices=list(knowledge.AREAS), default=None)
    p.add_argument("--scope", choices=list(knowledge.SCOPES), default="repo")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="recall", help="Recall control methods that worked on this computer (once at task start)", run=cmd_recall,
            configure=configure_recall),
    Command(name="learn", help="Record methods that worked or failed (more accurate with use)", run=cmd_learn,
            configure=configure_learn),
    Command(name="forget", help="Forget a wrongly learned method", run=cmd_forget,
            configure=configure_forget),
]
