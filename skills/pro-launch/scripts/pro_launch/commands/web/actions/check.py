"""`web check` — turn a checkbox, radio or switch on (--off turns it off) and return the resulting state (#892)."""
from __future__ import annotations


from pro_launch.commands.web.element import locate_target, perform_on_target, target_wait_seconds
from pro_launch.commands.web.session import done_payload
from pro_launch.registry import Action

# Current checked state. null if the element cannot be checked
CHECKED_JS = """(e) => ('checked' in e && typeof e.checked === 'boolean' && e.tagName.toLowerCase() === 'input')
  ? e.checked : (e.hasAttribute('aria-checked') ? e.getAttribute('aria-checked') === 'true' : null)"""


def execute(page, args, state: dict) -> dict:
    element, info, failure = locate_target(page, args, state, "check", should_wait=True)
    if failure:
        return failure
    before = element.evaluate(CHECKED_JS)
    should_check = not args.off
    try:
        failure = perform_on_target(page, args, "check", info, lambda: element.set_checked(
            should_check, timeout=target_wait_seconds(args) * 1000))
        if failure:
            return failure
    except Exception as e:
        message = str(e)
        # Not a checkbox, or tried to turn a radio off — waiting will not help
        if "checkbox" in message.lower() or "radio" in message.lower():
            return {"ok": False, "code": "not_checkable", "action": "check", "target": info,
                    "url": page.url, "error": message[:300],
                    "next": "web inspect --role checkbox  # pick an element that can be checked"}
        raise
    after = element.evaluate(CHECKED_JS)
    payload = done_payload("check", page)
    payload.update({"target": info, "checked_before": before, "checked": after,
                    "summary": f"'{(info.get('text') or info.get('aria') or info.get('tag'))[:40]}' "
                               + ("on" if after else "off")})
    return payload


def configure(p) -> None:
    p.add_argument("--off", action="store_true", help="Turn off (default turns on)")


ACTION = Action(name="check", run=execute, configure=configure,
                options=("selector", "ref", "target_timeout", "confirm_mutating", "frame"),
                help="Turn a checkbox, radio or switch on (--off turns it off)",
                example="web check --ref 5 --off")
