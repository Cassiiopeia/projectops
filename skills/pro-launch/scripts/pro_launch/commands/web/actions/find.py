"""`web find` — 누를 만한 요소를 번호와 함께 돌려준다."""
from __future__ import annotations


from pro_launch.commands.web.frames import frame_scope, frames_hint
from pro_launch.commands.web.session import safe_title
from pro_launch.commands.web.targets import CLICKABLE, FIND_JS, REF_ATTR, is_mutating_target, role_selector
from pro_launch.registry import Action

# --all 일 때 후보 상한 — 무제한이면 큰 표가 출력을 덮는다
ALL_LIMIT = 500


def _web_find(page, args) -> dict:
    # --frame 이면 그 iframe 문서 안에서 찾는다 (#877)
    scope, failure = frame_scope(page, args, "find")
    if failure:
        return failure
    limit = ALL_LIMIT if args.all else args.limit
    # textbox · searchbox · input 은 ARIA role 속성이 없는 그냥 <input> 까지 잡도록 실제 요소 선택자로 바꾼다 (#930)
    mapped_selector = role_selector(args.role) if args.role and not args.selector else None
    res = scope.evaluate(FIND_JS, {"attr": REF_ATTR, "clickable": CLICKABLE, "text": args.text,
                                   "role": None if mapped_selector else args.role,
                                   "selector": mapped_selector or args.selector, "limit": limit})
    items = res.get("items") or []
    for it in items:
        it["mutating"] = is_mutating_target(it)
    if not items:
        # 주 키는 실패에도 둔다 — json.load(...)["items"] 파이프가 KeyError 로 죽었다 (#931)
        failure = {"ok": False, "code": "nothing_found", "action": "find", "items": [], "total": 0, "shown": 0,
                   "url": page.url, "title": safe_title(page),
                   "error": "No visible element matches",
                   "next": "web text  # read the screen text first, then search again with that text in --text"}
        if args.role in ("textbox", "searchbox", "input"):
            failure["next"] = "web inspect --role input  # read input boxes with their names and values"
        # 최상위에서 못 찾았는데 iframe 이 있으면 그 안일 수 있다 — 목록과 --frame 안내
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
    """열린 모달이 있으면 알린다 — 모달 안의 후보가 앞(in_modal: true)이고, 뒤의 것은 가려져 눌리지 않을 수 있다 (projectops#1023)."""
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
