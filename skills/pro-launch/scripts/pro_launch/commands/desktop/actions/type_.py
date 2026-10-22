"""`desktop type` — 입력칸(ref)에 값을 넣는다. 비밀 칸은 --cred · --text-env 로만 받는다."""
from __future__ import annotations

import desktop_input

from pro_launch.commands.desktop.common import masked, public_window, secret_text
from pro_launch.commands.desktop.input_ops import (STALE_REASONS, before_digest, ensure_front, finish,
                                                   keys_target_refusal, press_node, resolve_ref, stale_failure)
from pro_launch.registry import Action
from pro_launch.runtime.output import out


def execute(args) -> int:
    be = args.backend
    value, is_secret, failure = secret_text(args)
    if failure:
        return out(failure)
    if value is None:
        return out({"ok": False, "code": "text_required", "error": "Needs --text, --text-env or --cred"})
    window, node, failure = resolve_ref(be, args.ref)
    failure = failure or ensure_front(be, window)
    if failure:
        return out(failure)
    if node.get("secret") and not is_secret:
        return out({"ok": False, "code": "secret_requires_cred", "element": desktop_input.public_node(node),
                    "error": "This is a password field — plain --text would leave the value in the command line",
                    "next": f"desktop type --ref {args.ref} --cred <name>  # or --text-env VAR"})
    region = window["bounds"]
    before = before_digest(be, region)
    transport = "invoke"
    if "set_value" in (node.get("actions") or []) and not args.keys:
        ok, detail = be.perform(window, node, "set_value", value)
        if detail in STALE_REASONS:
            return out(stale_failure(detail))
    else:
        ok = False
    if not ok:
        # 값 패턴이 없거나 거부됐다 — 초점을 주고 글자를 보낸다. 마우스 없이 초점을 줄 수 있으면 그쪽이 먼저다
        # (다른 창이 칸을 덮고 있으면 클릭이 덮은 창에 떨어지고 키가 엉뚱한 칸으로 간다 — 실측)
        ok, detail = be.perform(window, node, "focus")
        transport, failure = "invoke", None
        if detail in STALE_REASONS:
            return out(stale_failure(detail))
        if not ok:
            ok, detail, transport, failure = press_node(be, window, node)
        failure = failure or (keys_target_refusal(be, window) if ok else None)
        if failure:
            return out(failure)
        if ok:
            ok, detail = be.type_text(value)
            transport = "keys"
    if ok and args.submit and transport != "keys":
        refusal = keys_target_refusal(be, window)
        if refusal:
            return out(refusal)
    if ok and args.submit:
        ok, detail = be.press("enter", [])
    payload = {"ok": ok, "code": "ok" if ok else "type_failed", "transport": transport,
               "detail": masked(detail, value if is_secret else None), "secret": is_secret,
               "element": desktop_input.public_node(node), "window": public_window(window),
               "summary": f"Typed into '{node.get('text') or node.get('role')}'" + (" (hidden value)" if is_secret else ""),
               "next": "desktop find --text \"<next button>\""}
    return out(finish(be, args, region, before, payload) if ok else payload)


def configure(p) -> None:
    p.add_argument("--ref", type=int, required=True, help="input field number from the last find/tree")
    p.add_argument("--text", default=None, help="plain text (not for passwords)")
    p.add_argument("--text-env", default=None, help="read the value from this environment variable (hidden)")
    p.add_argument("--cred", default=None, help="saved credential name (hidden)")
    p.add_argument("--cred-field", default=None, help="--cred: which field (default password)")
    p.add_argument("--submit", action="store_true", help="press Enter after typing")
    p.add_argument("--keys", action="store_true", help="type key by key even if the field accepts a value directly")


ACTION = Action(name="type", needs="nothing", run=execute, configure=configure,
                options=("shot",), device_use="mutate",
                help="Put text into an input field (password fields only via --cred / --text-env)",
                example="desktop type --ref 2 --text \"hello\" --submit")
