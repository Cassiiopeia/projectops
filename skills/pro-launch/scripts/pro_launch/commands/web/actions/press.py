"""`web press` — 키를 누른다. 대상을 주면 그 요소에서, 없으면 지금 초점에서 (#891)."""
from __future__ import annotations


from pro_launch.commands.web.element import locate_target, outcome_wait_seconds, perform_on_target, target_wait_seconds
from pro_launch.commands.web.session import safe_title, settle
from pro_launch.registry import Action

# 대상이 바꾸는 버튼일 때 누르는 것과 같은 키 — 읽기 전용에서 막는다
ACTIVATING_KEYS = {"enter", "space", " "}


def execute(page, args, state: dict) -> dict:
    if not args.key:
        return {"ok": False, "code": "missing_argument", "error": "--key 가 필요합니다 (Enter · Escape · Tab …)"}
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
                    "hint": "Enter · Escape · Tab · ArrowDown · Backspace · Control+A 처럼 Playwright 키 이름"}
        raise
    try:
        page.wait_for_load_state("domcontentloaded", timeout=3000)
    except Exception:
        pass
    page.wait_for_timeout(300)
    settle(page, state, outcome_wait_seconds(args))
    after_url, after_title = page.url, safe_title(page)
    changed = after_url != before_url or after_title != before_title
    return {"action": "press", "key": args.key, "target": info, "changed": changed,
            "before": {"url": before_url, "title": before_title}, "url": after_url, "title": after_title,
            "summary": f"{args.key} 누름 → " + ("주소·제목이 바뀌었다" if changed else "주소·제목 그대로"),
            "next": "web text  # 결과 화면을 읽는다"}


def configure(p) -> None:
    p.add_argument("--key", default=None, help="Enter · Escape · Tab · ArrowDown · Control+A 처럼 키 이름")


ACTION = Action(name="press", run=execute, configure=configure,
                options=("selector", "ref", "target_timeout", "confirm_mutating"),
                help="키를 누른다 — 대상을 주면 그 요소에서, 없으면 지금 초점에서",
                example="web press --ref 2 --key Enter")
