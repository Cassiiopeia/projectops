"""`web find` — return pressable elements with numbers."""
from __future__ import annotations


from pro_launch.commands.web.frames import frame_scope, frames_hint
from pro_launch.commands.web.session import safe_title
from pro_launch.commands.web.targets import CLICKABLE, FIND_JS, REF_ATTR, is_mutating_target, role_selector
from pro_launch.registry import Action

# Candidate cap with --all — unlimited lets a big table flood the output
ALL_LIMIT = 500


def _web_find(page, args) -> dict:
    # With --frame, search inside that iframe's document (#877)
    scope, failure = frame_scope(page, args, "find")
    if failure:
        return failure
    limit = ALL_LIMIT if args.all else args.limit
    # textbox · searchbox · input become real element selectors so plain <input> without an ARIA role is matched too (#930)
    mapped_selector = role_selector(args.role) if args.role and not args.selector else None
    res = scope.evaluate(FIND_JS, {"attr": REF_ATTR, "clickable": CLICKABLE, "text": args.text,
                                   "role": None if mapped_selector else args.role,
                                   "selector": mapped_selector or args.selector, "limit": limit})
    items = res.get("items") or []
    for it in items:
        it["mutating"] = is_mutating_target(it)
    if not items:
        # Keep the main key even on failure — json.load(...)["items"] pipes died with KeyError (#931)
        failure = {"ok": False, "code": "nothing_found", "action": "find", "items": [], "total": 0, "shown": 0,
                   "url": page.url, "title": safe_title(page),
                   "error": "No visible element matches",
                   "next": "web text  # read the screen text first, then search again with that text in --text"}
        if args.role in ("textbox", "searchbox", "input"):
            failure["next"] = "web inspect --role input  # read input boxes with their names and values"
        # Not found at top level but iframes exist — it may be inside; list them and suggest --frame
        if not args.frame:
            failure.update(frames_hint(page))
        return failure
    frame_flag = f" --frame '{args.frame}'" if args.frame else ""
    payload = {"action": "find", "items": items, "frame": args.frame, "total": res.get("total"), "shown": len(items),
               "fallback": res.get("fallback"), "url": page.url, "title": safe_title(page),
               "summary": f"{len(items)} candidates (of {res.get('total')})",
               "next": f"web click --ref <number>{frame_flag} --expect-url <part of the new URL>  # click only the chosen one"}
    _attach_modal(payload, res.get("modal"))
    return payload


def _attach_modal(payload: dict, modal: dict | None) -> None:
    """Report an open modal — candidates inside it come first (in_modal: true); the rest may be covered and not pressable (projectops#1023)."""
    if not modal:
        return
    payload["modal"] = modal
    inside = sum(1 for it in payload["items"] if it.get("in_modal"))
    if inside:
        payload["summary"] += f" — a {modal.get('kind') or 'modal'} is open; its {inside} candidate(s) come first (in_modal)"
    else:
        payload["summary"] += (f" — a {modal.get('kind') or 'modal'} is open but none of these are inside it; "
                               "they may be covered. Read the modal with web text first")


def configure(p) -> None:
    p.add_argument("--role", default=None,
                   help="find: narrow by role such as link · button · row · tab · textbox (input box)")
    p.add_argument("--limit", type=int, default=20, help="find: number of candidates to return")
    p.add_argument("--all", action="store_true", help=f"find: everything, no count limit (max {ALL_LIMIT})")


def execute(page, args, state: dict) -> dict:
    return _web_find(page, args)


ACTION = Action(name="find", run=execute, configure=configure, options=("text", "selector", "frame"),
                help="Return clickable elements with numbers (ref)",
                example='web find --text "Sign in"')
