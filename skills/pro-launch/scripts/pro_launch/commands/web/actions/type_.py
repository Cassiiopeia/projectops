"""`web type` — 입력창에 글자를 넣는다."""
from __future__ import annotations


from pro_launch.commands.web.element import locate_target, perform_on_target, target_wait_seconds
from pro_launch.commands.web.session import done_payload
from pro_launch.registry import Action


def execute(page, args, state: dict) -> dict:
    if not ((args.selector or args.ref is not None) and args.text is not None):
        return {"ok": False, "code": "missing_argument",
                "error": "--selector(또는 --ref) 와 --text 가 필요합니다"}
    # 입력창이 늦게 그려지는 화면이 있어 선택자는 붙기를 기다린다. 입력은 바꾸는 조작이 아니라 막지 않는다
    element, info, failure = locate_target(page, args, state, "type", should_wait=True,
                                           should_guard_mutating=False)
    if failure:
        return failure
    failure = perform_on_target(page, args, "type", info,
                                lambda: element.fill(args.text, timeout=target_wait_seconds(args) * 1000))
    if failure:
        return failure
    payload = done_payload(args.action, page)
    payload["target"] = info
    return payload


ACTION = Action(name="type", run=execute, options=("selector", "ref", "text", "secret_text", "target_timeout", "frame"),
                help="입력창에 글자를 넣는다 (비밀번호는 --text-env · --cred)",
                example="web type --ref 2 --text-env APP_PW")
