"""`web inspect` — read inputs, buttons, checkboxes, selects and links with name, value and state (read-only, #899).

`web find` picks what to press; this **reads the form** — what needs filling and what is disabled.
The returned `ref` works directly as --ref for click · type · check · select · hover (same data-pops-ref as find).
No arbitrary JS entry point — the fields read are fixed.
"""
from __future__ import annotations


from pro_launch.commands.web.frames import frame_scope
from pro_launch.commands.web.session import safe_title
from pro_launch.commands.web.targets import (INSPECT_JS, MAXIMUM_OPTIONS, REF_ATTR, ROLE_ALIASES, ROLE_CHOICES,
                                             ROLE_SELECTORS)
from pro_launch.registry import Action

# Max items returned at once — beyond that, report truncated
MAXIMUM_LIMIT = 100


def _web_inspect(page, args) -> dict:
    args.role = ROLE_ALIASES.get(args.role, args.role)   # common names like textbox · searchbox (#930)
    limit = max(1, min(args.limit, MAXIMUM_LIMIT))
    # With --frame, the form inside that iframe (#877)
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
