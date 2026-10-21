"""`web inspect` — 입력창·버튼·체크·선택·링크를 이름·값·상태와 함께 읽는다 (읽기 전용, #899).

`web find` 는 누를 것을 고르고, 이것은 **폼을 읽는다** — 무엇을 채워야 하고 무엇이 비활성인지.
돌려준 `ref` 는 click · type · check · select · hover 의 --ref 로 그대로 쓴다 (find 와 같은 data-pops-ref).
임의 JS 실행 창구는 두지 않는다 — 읽는 항목이 고정돼 있다.
"""
from __future__ import annotations


from pro_launch.commands.web.frames import frame_scope
from pro_launch.commands.web.session import safe_title
from pro_launch.commands.web.targets import (INSPECT_JS, MAXIMUM_OPTIONS, REF_ATTR, ROLE_ALIASES, ROLE_CHOICES,
                                             ROLE_SELECTORS)
from pro_launch.registry import Action

# 한 번에 돌려줄 최대 개수 — 넘으면 truncated 로 알린다
MAXIMUM_LIMIT = 100


def _web_inspect(page, args) -> dict:
    args.role = ROLE_ALIASES.get(args.role, args.role)   # textbox · searchbox 같은 흔한 이름 (#930)
    limit = max(1, min(args.limit, MAXIMUM_LIMIT))
    # --frame 이면 그 iframe 안의 폼 (#877)
    scope, failure = frame_scope(page, args, "inspect")
    if failure:
        return failure
    res = scope.evaluate(INSPECT_JS, {"attr": REF_ATTR, "roles": ROLE_SELECTORS, "role": args.role,
                                      "near": args.near, "limit": limit, "maxOptions": MAXIMUM_OPTIONS})
    items = res.get("items") or []
    total = res.get("total") or 0
    if args.near and res.get("anchor_found") is False:
        return {"ok": False, "code": "near_not_found", "action": "inspect", "url": page.url,
                "error": f"Text '{args.near}' is not on the screen",
                "next": f'web text --grep "{args.near}"  # check the text that is really on the screen'}
    if not items:
        return {"ok": False, "code": "nothing_found", "action": "inspect", "items": [], "total": 0, "shown": 0,
                "url": page.url, "title": safe_title(page), "error": f"No visible {args.role} element",
                "next": "web inspect --role all"}
    return {"action": "inspect", "role": args.role, "near": args.near, "items": items,
            "shown": len(items), "total": total, "truncated": total > len(items),
            "url": page.url, "title": safe_title(page),
            "summary": f"{len(items)} {args.role} (of {total})",
            "next": "web type --ref <number> --text <value> · web check --ref <number> · web select --ref <number> --value <value>"}


def configure(p) -> None:
    p.add_argument("--role", choices=(*ROLE_CHOICES, *ROLE_ALIASES), default="all",
                   help="Kind to read (default all). textbox · searchbox mean input, radio · switch mean checkbox")
    p.add_argument("--near", default=None, help="Closest to this text first (labels containing it come first)")
    p.add_argument("--limit", type=int, default=40, help=f"Maximum number to return (max {MAXIMUM_LIMIT})")


def execute(page, args, state: dict) -> dict:
    return _web_inspect(page, args)


ACTION = Action(name="inspect", run=execute, configure=configure, options=("frame",),
                help="Read inputs, buttons, checkboxes, selects and links with name, value, state and ref (read-only)",
                example='web inspect --role input --near "Email"')
