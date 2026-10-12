"""`web route` — 응답을 바꿔치기해 빈 목록·실패·지연을 연출한다."""
from __future__ import annotations

import json
import re
from pathlib import Path

from pro_launch.registry import Action
from pro_launch.runtime.browser import write_state
from pro_launch.runtime.output import out


def _looks_like_path(text: str) -> bool:
    """JSON·문장이 아니라 파일 경로처럼 보이나. 공백·따옴표·괄호가 없고 슬래시나 확장자가 있으면 경로로 본다."""
    t = text.strip()
    if not t or re.search(r"[\s{}\[\]\"<>]", t):
        return False
    try:
        json.loads(t)    # 1.5 · true 같은 JSON 값은 파일명이 아니라 본문이다
        return False
    except json.JSONDecodeError:
        pass
    return "/" in t or "\\" in t or bool(re.search(r"\.[A-Za-z0-9]{1,5}$", t))


def _web_route(args, state: dict, state_f: Path) -> int:
    """응답 바꿔치기 — 빈 목록·실패·지연을 서버를 건드리지 않고 연출한다."""
    rules = list(state.get("routes") or [])
    if args.clear:
        state["routes"] = []
        write_state(state_f, state)
        return out({"action": "route", "routes": [],
                    "summary": f"바꿔치기 규칙 {len(rules)}개를 지웠습니다",
                    "next": "web goto  # 진짜 응답으로 다시 그립니다"})
    if not args.match:
        return out({"action": "route", "routes": rules,
                    "summary": f"규칙 {len(rules)}개",
                    "hint": "--match '**/api/items*' --status 200 --body empty.json 처럼 겁니다"})
    if args.status is None and not args.delay:
        return out({"ok": False, "code": "missing_argument",
                    "error": "--status 나 --delay 중 하나는 있어야 합니다"})
    if args.status is not None and not 100 <= args.status <= 599:
        return out({"ok": False, "code": "bad_status",
                    "error": f"--status 는 100~599 여야 합니다 ({args.status})"})
    if args.delay is not None and args.delay < 0:
        return out({"ok": False, "code": "bad_delay", "error": f"--delay 는 0 이상이어야 합니다 ({args.delay})"})
    body, ctype = "", "application/json"
    if args.body_text is not None:
        body = args.body_text   # 경로 오타와 구분되도록 인라인 본문은 이 옵션으로 명시한다
    elif args.body:
        bf = Path(args.body)
        if bf.is_file():
            body = bf.read_text(encoding="utf-8")
        elif _looks_like_path(args.body):
            # 오타 경로가 조용히 가짜 응답 본문이 되면 연출 결과가 통째로 틀어진다 (#711)
            return out({"ok": False, "code": "body_not_found",
                        "error": f"--body 파일이 없습니다: {args.body}",
                        "next": "경로를 확인한다. 글자 그대로 본문으로 쓰려면 --body-text 를 쓴다"})
        else:
            body = args.body   # 짧은 JSON 본문은 그대로 받는다: --body '[]'
    if body:
        try:
            json.loads(body)
        except json.JSONDecodeError:
            ctype = "text/plain; charset=utf-8"
    rule = {"match": args.match, "status": args.status, "body": body,
            "content_type": ctype, "delay_ms": args.delay or 0}
    rules = [r for r in rules if r.get("match") != args.match] + [rule]
    state["routes"] = rules
    write_state(state_f, state)
    return out({"action": "route", "rule": {k: v for k, v in rule.items() if k != "body"},
                "body_bytes": len(body.encode("utf-8")), "routes": len(rules),
                "summary": f"{args.match} → {args.status or '지연 ' + str(args.delay) + 'ms'}",
                "next": "web goto --url <그 화면>  # 규칙은 이동할 때 걸린다. 이미 열린 화면은 다시 불러야 한다"})


def configure(p) -> None:
    p.add_argument("--match", default=None, help="route: 바꿔칠 요청 주소 glob. 예 **/api/items*")
    p.add_argument("--status", type=int, default=None, help="route: 돌려줄 상태 코드")
    p.add_argument("--body", default=None, help="route: 돌려줄 본문 (파일 경로 또는 짧은 문자열)")
    p.add_argument("--body-text", dest="body_text", default=None,
                   help="route: 글자 그대로 돌려줄 본문 (파일 경로로 읽지 않는다)")
    p.add_argument("--delay", type=int, default=0, help="route: 응답 지연(ms) — 로딩 상태 연출")


ACTION = Action(name="route", needs="state_offline", run=_web_route, configure=configure)
