"""`web check` — 체크박스·라디오·스위치를 켜거나(--off 면 끈다) 결과 상태를 돌려준다 (#891)."""
from __future__ import annotations


from pro_launch.commands.web.element import locate_target
from pro_launch.commands.web.session import done_payload
from pro_launch.registry import Action

# 지금 체크 상태. 체크할 수 없는 요소면 null
CHECKED_JS = """(e) => ('checked' in e && typeof e.checked === 'boolean' && e.tagName.toLowerCase() === 'input')
  ? e.checked : (e.hasAttribute('aria-checked') ? e.getAttribute('aria-checked') === 'true' : null)"""


def execute(page, args, state: dict) -> dict:
    element, info, failure = locate_target(page, args, state, "check", should_wait=True)
    if failure:
        return failure
    before = element.evaluate(CHECKED_JS)
    should_check = not args.off
    try:
        element.set_checked(should_check, timeout=args.timeout * 1000)
    except Exception as e:
        message = str(e)
        # 체크박스가 아니거나 라디오를 끄려 했다 — 기다려도 안 되는 일이다
        if "checkbox" in message.lower() or "radio" in message.lower():
            return {"ok": False, "code": "not_checkable", "action": "check", "target": info,
                    "url": page.url, "error": message[:300],
                    "next": "web inspect --role checkbox  # 체크할 수 있는 요소를 고른다"}
        raise
    after = element.evaluate(CHECKED_JS)
    payload = done_payload("check", page)
    payload.update({"target": info, "checked_before": before, "checked": after,
                    "summary": f"'{(info.get('text') or info.get('aria') or info.get('tag'))[:40]}' "
                               + ("켬" if after else "끔")})
    return payload


def configure(p) -> None:
    p.add_argument("--off", action="store_true", help="끈다 (기본은 켠다)")


ACTION = Action(name="check", run=execute, configure=configure,
                options=("selector", "ref", "timeout", "confirm_mutating"),
                help="체크박스·라디오·스위치를 켠다 (--off 면 끈다)",
                example="web check --ref 5 --off")
