"""`web find` — 누를 만한 요소를 번호와 함께 돌려준다."""
from __future__ import annotations


from pro_launch.commands.web.session import safe_title
from pro_launch.commands.web.targets import CLICKABLE, FIND_JS, REF_ATTR, is_mutating_target
from pro_launch.registry import Action


def _web_find(page, args) -> dict:
    res = page.evaluate(FIND_JS, {"attr": REF_ATTR, "clickable": CLICKABLE, "text": args.text,
                                   "role": args.role, "selector": args.selector, "limit": args.limit})
    items = res.get("items") or []
    for it in items:
        it["mutating"] = is_mutating_target(it)
    if not items:
        return {"ok": False, "code": "nothing_found", "action": "find", "url": page.url, "title": safe_title(page),
                "error": "조건에 맞는 보이는 요소가 없습니다",
                "next": "web text  # 화면 글자를 먼저 읽고 --text 를 그 글자로 다시 찾는다"}
    return {"action": "find", "items": items, "total": res.get("total"), "shown": len(items),
            "fallback": res.get("fallback"), "url": page.url, "title": safe_title(page),
            "summary": f"후보 {len(items)}개 (전체 {res.get('total')})",
            "next": "web click --ref <번호> --expect-url <바뀔 주소 일부>  # 고른 것만 누른다"}


def configure(p) -> None:
    p.add_argument("--role", default=None, help="find: link · button · row · tab 처럼 역할로 좁힌다")
    p.add_argument("--limit", type=int, default=20, help="find: 돌려줄 후보 수")


def execute(page, args, state: dict) -> dict:
    return _web_find(page, args)


ACTION = Action(name="find", run=execute, configure=configure)
