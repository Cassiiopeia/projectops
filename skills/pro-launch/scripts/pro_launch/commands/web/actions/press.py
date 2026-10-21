"""`web press` — 키를 누른다. 대상을 주면 그 요소에서, 없으면 지금 초점에서 (#892)."""
from __future__ import annotations


from pro_launch.commands.web.element import locate_target, outcome_wait_seconds, perform_on_target, target_wait_seconds
from pro_launch.commands.web.session import safe_title, settle
from pro_launch.registry import Action

# 대상이 바꾸는 버튼일 때 누르는 것과 같은 키 — 읽기 전용에서 막는다
ACTIVATING_KEYS = {"enter", "space", " "}


def execute(page, args, state: dict) -> dict:
    if not args.key:
        return {"ok": False, "code": "missing_argument", "error": "--key is required (Enter · Escape · Tab …)"}
    has_target = args.ref is not None or bool(args.selector)
    element, info = None, None
    if has_target:
        element, info, failure = locate_target(
            page, args, state, "press", should_wait=True,
            should_guard_mutating=args.key.lower() in ACTIVATING_KEYS)
        if failure:
            return failure
    before_url, before_title = page.url, safe_title(page)
    try:
        if element is not None:
            failure = perform_on_target(page, args, "press", info, lambda: element.press(
                args.key, timeout=target_wait_seconds(args) * 1000))
            if failure:
                return failure
        else:
            page.keyboard.press(args.key)
    except Exception as e:
        if "Unknown key" in str(e):
            return {"ok": False, "code": "bad_key", "action": "press", "error": str(e)[:200],
                    "hint": "Playwright key names such as Enter · Escape · Tab · ArrowDown · Backspace · Control+A"}
        raise
    try:
        page.wait_for_load_state("domcontentloaded", timeout=3000)
    except Exception:
        pass  # 로드 신호가 늦어도 아래 짧은 대기로 넘어간다
    page.wait_for_timeout(300)
    settle(page, state, outcome_wait_seconds(args))
    after_url, after_title = page.url, safe_title(page)
    changed = after_url != before_url or after_title != before_title
    return {"action": "press", "key": args.key, "target": info, "changed": changed,
            "before": {"url": before_url, "title": before_title}, "url": after_url, "title": after_title,
            "summary": f"Pressed {args.key} → " + ("URL or title changed" if changed else "URL and title unchanged"),
            "next": "web text  # read the resulting screen"}


def configure(p) -> None:
    p.add_argument("--key", default=None, help="Key name such as Enter · Escape · Tab · ArrowDown · Control+A")


ACTION = Action(name="press", run=execute, configure=configure,
                options=("selector", "ref", "target_timeout", "confirm_mutating", "capture_requests"),
                help="Press a key — on the target if given, otherwise at the current focus",
                example="web press --ref 2 --key Enter")
