"""`web type` — 입력창에 글자를 넣는다."""
from __future__ import annotations


from pro_launch.commands.web.session import done_payload
from pro_launch.registry import Action


def execute(page, args, state: dict) -> dict:
    if not (args.selector and args.text is not None):
        return {"ok": False, "code": "missing_argument",
                "error": "--selector 와 --text 가 필요합니다"}
    page.fill(args.selector, args.text, timeout=args.timeout * 1000)
    return done_payload(args.action, page)


ACTION = Action(name="type", run=execute)
