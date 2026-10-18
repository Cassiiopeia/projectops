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
                    "summary": (f"'{args.match}' 가 든 기억이 없다" if args.match
                                else "이 컴퓨터에서 쌓인 방법이 아직 없다"),
                    "next": "작업이 끝나면 launch_cli.py learn 으로 먹힌 방법을 남긴다"})
    return out({"ok": True, "code": "ok", "entries": rows,
                "summary": f"{len(rows)}건 (verify:true 는 한 번 확인하고 쓴다"
                           + (", detail_path 는 긴 경위 노트 — 필요하면 읽는다)" if any("detail_path" in r for r in rows)
                              else ")"),
                "next": "먹혔는지 안 먹혔는지 learn --result ok|fail 로 알린다"})


def _supersede(args) -> int:
    """learn --supersede KEY --by X: 항목을 지우지 않고 X(kb:<id> · feature:<명령>)로 대체됐다고 표시."""
    if not args.by:
        return out({"ok": False, "code": "by_required", "error": "--supersede 에는 --by 가 필요하다",
                    "next": "learn --supersede <key> --by kb:<id>  # 또는 feature:<명령>"})
    path = knowledge.store_path(args.scope, project_root(args))
    marked = knowledge_stale.mark_superseded(path, args.supersede, args.by, area=args.area)
    return out({"ok": bool(marked), "code": "ok" if marked else "not_found", "marked": marked,
                "summary": f"{args.supersede} 를 {args.by} 로 대체 표시" if marked else "그런 항목이 없다",
                "next": "recall  # 대체된 항목은 맨 뒤로 가고 응답에는 실리지 않는다" if marked else None})


def cmd_learn(args) -> int:
    args.scope = _learn_scope(args)
    if args.supersede:
        return _supersede(args)
    missing = [name for name in ("area", "key", "how", "result") if not getattr(args, name)]
    if missing:
        return out({"ok": False, "code": "bad_args",
                    "error": f"learn 에는 --{', --'.join(missing)} 가 필요하다",
                    "next": "learn --area <영역> --key <키> --how <방법> --result ok|fail"})
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
    note = (f" — 다른 레포의 같은 지식 {r['promoted_from']}건과 합쳐 이 컴퓨터 범위로 올렸다"
            if r.get("promoted_from") else "")
    rel = r.get("related") or []
    return out({"ok": True, "code": "ok", "entry": e, "scope": r["scope"],
                "promoted_from": r.get("promoted_from", 0), "related": rel or None,
                "summary": f"{e['key']} ok={e['ok']} fail={e['fail']} ({r['scope']}){note}",
                # 비슷한 기억이 있으면 같은 지식인지 agent 가 판단한다 — 도구가 애매한 것을 멋대로 합치지 않는다
                "next": (f"related 중 같은 지식이 있으면 forget --key <방금 key> 후 "
                         f"learn --scope machine --key <그 key> 로 합친다" if rel else None)})


def _read_detail(args) -> tuple[str | None, dict | None]:
    """--detail 글 또는 --detail-file 파일 내용 > (본문, 실패 결과)."""
    if not getattr(args, "detail_file", None):
        return args.detail, None
    try:
        return Path(args.detail_file).read_text(encoding="utf-8"), None
    except OSError as e:
        return None, {"ok": False, "code": "file_unreadable", "error": str(e),
                      "next": "--detail 로 직접 넘기거나 파일 경로를 고친다"}


def _learn_retry_hint(result: dict) -> str:
    """거절 사유별 다음 행동."""
    if result["error"] == "too_long":
        return ("how 는 한 줄 결론만 남기고, 왜 막혔고 어떻게 풀었는지는 "
                "--detail \"<긴 글>\" (또는 --detail-file <파일>) 로 같이 넘긴다")
    if result["error"] == "secret_detected":
        return "matched_span 의 값 부분을 빼거나 <비밀번호> 처럼 바꿔 다시 부른다 (계정은 cred 에 둔다)"
    return "내용을 고쳐 다시 부른다"


def cmd_forget(args) -> int:
    args.scope = _learn_scope(args)
    path = knowledge.store_path(args.scope, project_root(args))
    if args.by:
        # 지우지 않고 대체 표시만 (--by kb:<id> · feature:<명령>)
        n = knowledge_stale.mark_superseded(path, args.key, args.by, area=args.area)
        return out({"ok": True, "code": "ok" if n else "not_found", "marked": n,
                    "summary": f"{n}건 대체 표시" if n else "그런 항목이 없다", "next": None})
    n = knowledge.forget(path, args.key, args.area)
    return out({"ok": True, "code": "ok" if n else "not_found", "removed": n,
                "summary": f"{n}건 지움" if n else "그런 항목이 없다", "next": None})


def configure_recall(p) -> None:
    # --platform 은 --area 의 별칭 (추측으로 많이 쓰는 이름, #931)
    p.add_argument("--area", "--platform", dest="area", choices=list(knowledge.AREAS), default=None)
    p.add_argument("--limit", type=int, default=knowledge.DEFAULT_LIMIT)
    p.add_argument("--match", default=None, help="키·방법·노트에 이 낱말이 든 것만 (예: swipe)")
    p.add_argument("--scope", choices=["both", "repo", "machine"], default="both")
    p.add_argument("--root", default=".")


def configure_learn(p) -> None:
    # area·key·how·result 는 --supersede 일 때만 생략한다 — cmd_learn 이 확인
    p.add_argument("--area", choices=list(knowledge.AREAS), default=None)
    p.add_argument("--key", default=None, help="한 줄 이름 (예: ios.tap)")
    p.add_argument("--how", default=None, help=f"방법 ({knowledge.MAX_HOW}자 이내, 비밀값 금지)")
    p.add_argument("--result", choices=["ok", "fail"], default=None)
    p.add_argument("--supersede", default=None, metavar="KEY", help="이 key 를 지우지 않고 --by 로 대체됐다고 표시")
    p.add_argument("--by", default=None, help="대체한 것: kb:<id> · feature:<명령> (--supersede · forget 용)")
    p.add_argument("--detail", default=None,
                   help=f"긴 경위·이유 ({knowledge.MAX_DETAIL}자 이내) — notes/<key>.md 에 두고 recall 이 경로를 준다")
    p.add_argument("--detail-file", default=None, help="--detail 대신 UTF-8 파일 (줄바꿈이 많은 글)")
    p.add_argument("--scope", choices=list(knowledge.SCOPES), default="repo")
    p.add_argument("--root", default=".")


def configure_forget(p) -> None:
    p.add_argument("--key", required=True)
    p.add_argument("--by", default=None, help="지우지 않고 kb:<id> · feature:<명령> 으로 대체 표시만")
    p.add_argument("--area", choices=list(knowledge.AREAS), default=None)
    p.add_argument("--scope", choices=list(knowledge.SCOPES), default="repo")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="recall", help="이 컴퓨터에서 먹힌 조작 방식을 꺼낸다 (작업 시작 때 한 번)", run=cmd_recall,
            configure=configure_recall),
    Command(name="learn", help="먹힌·안 먹힌 방식을 남긴다 (쓸수록 정확해진다)", run=cmd_learn,
            configure=configure_learn),
    Command(name="forget", help="잘못 배운 방식을 지운다", run=cmd_forget,
            configure=configure_forget),
]
