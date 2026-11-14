"""`web value` — save an input's or element's value without printing it (#930).

Values only inside an input, like a Client Secret, do not appear in `web text`, and OCR misread I/l. The value is written only to a 0600 file
in the state folder; the result carries only its length and a sha256 prefix. To put it into another input, use `web type --text-env NAME`.
"""
from __future__ import annotations

import hashlib

from pro_launch.commands.web.element import locate_target
from pro_launch.commands.web.saved_values import invalid_name_failure, is_valid_env_name, save_value, saved_next
from pro_launch.commands.web.session import done_payload
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root

# value for inputs, visible text for anything else (e.g. a code box next to a copy button)
READ_VALUE_JS = "(e) => (typeof e.value === 'string' ? e.value : (e.innerText || e.textContent || ''))"


def execute(page, args, state: dict) -> dict:
    if args.save_env and not is_valid_env_name(args.save_env):
        return invalid_name_failure("value", args.save_env)
    # Read-only — not blocked even in read-only sessions
    element, info, failure = locate_target(page, args, state, "value", should_wait=True, should_guard_mutating=False)
    if failure:
        return failure
    value = element.evaluate(READ_VALUE_JS)
    info["text"] = ""   # The input description's text holds the value as is — clear it so the value does not leak into the result
    if value is None or value == "":
        return {"ok": False, "code": "value_empty", "action": "value", "target": info, "url": page.url,
                "error": "The value is empty", "next": "web inspect  # pick the input box that holds the value"}
    payload = done_payload("value", page)
    payload["target"] = info
    if args.save_env:
        payload.update(save_value(project_root(args), args.save_env, value))
        payload["summary"] = f"Saved {len(value)} chars as {args.save_env} (not printed)"
        payload["next"] = saved_next(args.save_env)
    else:
        # Without a save name, keep the value nowhere and report only its shape
        payload.update({"length": len(value), "sha256_prefix": hashlib.sha256(value.encode("utf-8")).hexdigest()[:12],
                        "summary": f"Value has {len(value)} chars (not saved)",
                        "next": "web value --ref <number> --save-env NAME  # save the value without printing it"})
    return payload


def configure(p) -> None:
    p.add_argument("--save-env", dest="save_env", default=None,
                   help="Save the value under this name (not printed). Reuse it with web type --text-env NAME")


ACTION = Action(name="value", run=execute, configure=configure, options=("selector", "ref", "target_timeout", "frame"),
                help="Save an input or element value without printing it (shows only length · hash)",
                example="web value --selector '#client-secret' --save-env CLIENT_SECRET")
