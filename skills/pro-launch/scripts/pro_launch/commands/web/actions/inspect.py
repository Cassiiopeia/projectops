"""`web inspect` — 입력창·버튼·체크·선택·링크를 이름·값·상태와 함께 읽는다 (읽기 전용, #899).

`web find` 는 누를 것을 고르고, 이것은 **폼을 읽는다** — 무엇을 채워야 하고 무엇이 비활성인지.
돌려준 `ref` 는 click · type · check · select · hover 의 --ref 로 그대로 쓴다 (find 와 같은 data-pops-ref).
임의 JS 실행 창구는 두지 않는다 — 읽는 항목이 고정돼 있다.
"""
from __future__ import annotations


from pro_launch.commands.web.session import safe_title
from pro_launch.commands.web.targets import INSPECT_JS, MAXIMUM_OPTIONS, REF_ATTR, ROLE_CHOICES, ROLE_SELECTORS
from pro_launch.registry import Action

# 한 번에 돌려줄 최대 개수 — 넘으면 truncated 로 알린다
MAXIMUM_LIMIT = 100


def _web_inspect(page, args) -> dict:
    limit = max(1, min(args.limit, MAXIMUM_LIMIT))
    res = page.evaluate(INSPECT_JS, {"attr": REF_ATTR, "roles": ROLE_SELECTORS, "role": args.role,
                                      "near": args.near, "limit": limit, "maxOptions": MAXIMUM_OPTIONS})
    items = res.get("items") or []
    total = res.get("total") or 0
    if args.near and res.get("anchor_found") is False:
        return {"ok": False, "code": "near_not_found", "action": "inspect", "url": page.url,
                "error": f"'{args.near}' 글자가 화면에 없습니다",
                "next": f'web text --grep "{args.near}"  # 화면에 실제로 있는 글자를 확인한다'}
    if not items:
        return {"ok": False, "code": "nothing_found", "action": "inspect", "url": page.url,
                "title": safe_title(page), "error": f"보이는 {args.role} 요소가 없습니다",
                "next": "web inspect --role all"}
    return {"action": "inspect", "role": args.role, "near": args.near, "items": items,
            "shown": len(items), "total": total, "truncated": total > len(items),
            "url": page.url, "title": safe_title(page),
            "summary": f"{args.role} {len(items)}개 (전체 {total})",
            "next": "web type --ref <번호> --text <값> · web check --ref <번호> · web select --ref <번호> --value <값>"}


def configure(p) -> None:
    p.add_argument("--role", choices=ROLE_CHOICES, default="all", help="읽을 종류 (기본 all)")
    p.add_argument("--near", default=None, help="이 글자 가까이 있는 것부터 (라벨에 그 글자가 있으면 맨 앞)")
    p.add_argument("--limit", type=int, default=40, help=f"돌려줄 최대 개수 (최대 {MAXIMUM_LIMIT})")


def execute(page, args, state: dict) -> dict:
    return _web_inspect(page, args)


ACTION = Action(name="inspect", run=execute, configure=configure, options=(),
                help="입력창·버튼·체크·선택·링크를 이름·값·상태·ref 와 함께 읽는다 (읽기 전용)",
                example='web inspect --role input --near "이메일"')
