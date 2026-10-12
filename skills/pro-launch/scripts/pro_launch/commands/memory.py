"""`recall` · `learn` · `tidy` · `forget` — 이 컴퓨터에서 먹힌 조작 방식을 기억한다."""
from __future__ import annotations


from common.state import repo_unknown

import knowledge

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
    rows = knowledge.recall(_knowledge_paths(args), args.area, args.limit)
    if not rows:
        return out({"ok": True, "code": "empty", "entries": [],
                    "summary": "이 컴퓨터에서 쌓인 방법이 아직 없다",
                    "next": "작업이 끝나면 launch_cli.py learn 으로 먹힌 방법을 남긴다"})
    return out({"ok": True, "code": "ok", "entries": rows,
                "summary": f"{len(rows)}건 (verify:true 는 한 번 확인하고 쓴다)",
                "next": "먹혔는지 안 먹혔는지 learn --result ok|fail 로 알린다"})


def cmd_learn(args) -> int:
    args.scope = _learn_scope(args)
    repo_path = None if args.scope == "machine" else knowledge.store_path("repo", project_root(args))
    r = knowledge.learn_smart(repo_path, args.area, args.key, args.how, args.result, args.scope)
    if "error" in r:
        return out({"ok": False, "code": r["error"], "error": r["message"],
                    "next": "내용을 고쳐 다시 부른다"})
    e = r["entry"]
    note = (f" — 다른 레포의 같은 지식 {r['promoted_from']}건과 합쳐 이 컴퓨터 범위로 올렸다"
            if r.get("promoted_from") else "")
    rel = r.get("related") or []
    return out({"ok": True, "code": "ok", "entry": e, "scope": r["scope"],
                "promoted_from": r.get("promoted_from", 0), "related": rel or None,
                "summary": f"{e['key']} ok={e['ok']} fail={e['fail']} ({r['scope']}){note}",
                # 비슷한 기억이 있으면 같은 지식인지 agent 가 판단한다 — 도구가 애매한 것을 멋대로 합치지 않는다
                "next": (f"related 중 같은 지식이 있으면 forget --key <방금 key> 후 "
                         f"learn --scope machine --key <그 key> 로 합친다" if rel else None)})


def cmd_tidy(args) -> int:
    """흩어진 기억을 정리한다 — 여러 레포에 걸친 것과 잘못된 버킷을 이 컴퓨터 범위로 합친다."""
    r = knowledge.tidy()
    return out({"ok": True, "code": "ok", **r,
                "summary": f"{r['moved_to_machine']}건을 이 컴퓨터 범위로 옮김 (합친 것 {r['merged']}건)",
                "next": "recall --scope machine  # 결과를 본다"})


def cmd_forget(args) -> int:
    args.scope = _learn_scope(args)
    path = knowledge.store_path(args.scope, project_root(args))
    n = knowledge.forget(path, args.key, args.area)
    return out({"ok": True, "code": "ok" if n else "not_found", "removed": n,
                "summary": f"{n}건 지움" if n else "그런 항목이 없다", "next": None})


def configure_recall(p) -> None:
    p.add_argument("--area", choices=list(knowledge.AREAS), default=None)
    p.add_argument("--limit", type=int, default=knowledge.DEFAULT_LIMIT)
    p.add_argument("--scope", choices=["both", "repo", "machine"], default="both")
    p.add_argument("--root", default=".")


def configure_learn(p) -> None:
    p.add_argument("--area", required=True, choices=list(knowledge.AREAS))
    p.add_argument("--key", required=True, help="한 줄 이름 (예: ios.tap)")
    p.add_argument("--how", required=True, help=f"방법 ({knowledge.MAX_HOW}자 이내, 비밀값 금지)")
    p.add_argument("--result", required=True, choices=["ok", "fail"])
    p.add_argument("--scope", choices=list(knowledge.SCOPES), default="repo")
    p.add_argument("--root", default=".")


def configure_tidy(p) -> None:
    p.add_argument("--root", default=".")


def configure_forget(p) -> None:
    p.add_argument("--key", required=True)
    p.add_argument("--area", choices=list(knowledge.AREAS), default=None)
    p.add_argument("--scope", choices=list(knowledge.SCOPES), default="repo")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="recall", help="이 컴퓨터에서 먹힌 조작 방식을 꺼낸다 (작업 시작 때 한 번)", run=cmd_recall,
            configure=configure_recall),
    Command(name="learn", help="먹힌·안 먹힌 방식을 남긴다 (쓸수록 정확해진다)", run=cmd_learn,
            configure=configure_learn),
    Command(name="tidy", help="흩어진 기억을 정리한다 (여러 레포에 걸친 것 → 이 컴퓨터 범위)", run=cmd_tidy,
            configure=configure_tidy),
    Command(name="forget", help="잘못 배운 방식을 지운다", run=cmd_forget,
            configure=configure_forget),
]
