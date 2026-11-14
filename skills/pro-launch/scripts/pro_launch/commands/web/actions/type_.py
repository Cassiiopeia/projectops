"""`web type` — put text into an input. `--keys` types key by key (for places where fill does not work, like xterm or code editors, #930)."""
from __future__ import annotations


from pro_launch.commands.web.element import locate_target, perform_on_target, target_wait_seconds
from pro_launch.commands.web.session import done_payload
from pro_launch.registry import Action

# Default delay between keystrokes (ms) — slow enough for terminal emulators to keep up
DEFAULT_KEY_DELAY_MILLISECONDS = 60
# Time for the page's input handling to run before checking the value stayed (ms)
VALUE_SETTLE_MILLISECONDS = 300
# Current value of the input (text for contenteditable)
READ_VALUE_JS = "(e) => ('value' in e ? e.value : e.innerText) || ''"


def value_status(page, element) -> str:
    """kept · cleared · gone. A reformatted value (e.g. phone number hyphens) counts as kept — cleared only when empty"""
    page.wait_for_timeout(VALUE_SETTLE_MILLISECONDS)
    try:
        return "kept" if (element.evaluate(READ_VALUE_JS) or "").strip() else "cleared"
    except Exception:
        return "gone"


def retype_key_by_key(element, args) -> None:
    """Fields that wipe a fill value, like chip inputs — press it like a human so it gets key events (#1094)"""
    timeout_milliseconds = target_wait_seconds(args) * 1000
    element.click(timeout=timeout_milliseconds)
    element.press_sequentially(args.text, delay=DEFAULT_KEY_DELAY_MILLISECONDS,
                               timeout=timeout_milliseconds + len(args.text) * DEFAULT_KEY_DELAY_MILLISECONDS)


def value_not_kept_failure(page, info: dict | None, status: str) -> dict:
    is_gone = status == "gone"
    return {"ok": False, "code": "typed_value_not_kept", "action": "type", "target": info, "url": page.url,
            "error": ("The input box disappeared right after typing (the page re-rendered or reloaded)" if is_gone
                      else "The text did not stay in the input box, even when typed key by key"),
            "next": "web find  # pick the box again from the current screen, or do typing and the next step in one web script"}


def _type_keys(page, args, state: dict) -> dict:
    """--keys: type key by key into the target (or current focus). Unlike fill, keydown/keyup fire"""
    delay = args.delay_ms if args.delay_ms is not None else DEFAULT_KEY_DELAY_MILLISECONDS
    info = None
    if args.selector or args.ref is not None:
        element, info, failure = locate_target(page, args, state, "type", should_wait=True,
                                               should_guard_mutating=False)
        if failure:
            return failure
        failure = perform_on_target(page, args, "type", info, lambda: element.focus(
            timeout=target_wait_seconds(args) * 1000))
        if failure:
            return failure
    page.keyboard.type(args.keys, delay=delay)
    payload = done_payload("type", page)
    payload.update({"target": info, "mode": "keys", "typed_characters": len(args.keys), "delay_ms": delay,
                    "summary": f"Typed {len(args.keys)} keys ({delay}ms apart)",
                    "next": "web text  # check the input took effect (Enter: web press --key Enter)"})
    return payload


def execute(page, args, state: dict) -> dict:
    if args.keys is not None:
        return _type_keys(page, args, state)
    if not ((args.selector or args.ref is not None) and args.text is not None):
        return {"ok": False, "code": "missing_argument", "url": None,
                "error": "--selector (or --ref) and --text are required (to type key by key, use --keys)"}
    # Some screens render inputs late, so selectors wait for attach. Typing is not a changing action, so it is not blocked
    element, info, failure = locate_target(page, args, state, "type", should_wait=True,
                                           should_guard_mutating=False)
    if failure:
        return failure
    failure = perform_on_target(page, args, "type", info,
                                lambda: element.fill(args.text, timeout=target_wait_seconds(args) * 1000))
    if failure:
        return failure
    # Check the value really stayed before returning ok, so a field the page wiped is not reported as typed (#1094)
    status = value_status(page, element) if args.text.strip() else "kept"
    was_retyped = status == "cleared"
    if was_retyped:
        failure = perform_on_target(page, args, "type", info, lambda: retype_key_by_key(element, args))
        if failure:
            return failure
        status = value_status(page, element)
    if status != "kept":
        return value_not_kept_failure(page, info, status)
    payload = done_payload(args.action, page)
    payload["target"] = info
    if was_retyped:
        payload.update({"mode": "keys_fallback", "summary": "Typed key by key (this box cleared the pasted value)"})
    return payload


def configure(p) -> None:
    p.add_argument("--keys", default=None,
                   help="Type key by key (current focus if no target). For xterm · web terminals · editors — never for passwords")
    p.add_argument("--delay-ms", dest="delay_ms", type=int, default=None,
                   help=f"--keys: delay between keys (ms, default {DEFAULT_KEY_DELAY_MILLISECONDS})")


ACTION = Action(name="type", run=execute, configure=configure,
                options=("selector", "ref", "text", "secret_text", "target_timeout", "frame", "capture_requests"),
                help="Fill text into an input (passwords via --text-env · --cred, key by key via --keys)",
                example="web type --ref 2 --text-env APP_PW")
