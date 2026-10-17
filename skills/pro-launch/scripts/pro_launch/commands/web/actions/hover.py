"""`web hover` — 요소 위에 마우스를 올린다 (툴팁·펼침 메뉴, #891)."""
from __future__ import annotations


from pro_launch.commands.web.element import locate_target, perform_on_target, target_wait_seconds
from pro_launch.commands.web.session import done_payload
from pro_launch.registry import Action


def execute(page, args, state: dict) -> dict:
    # 올리기만 한다 — 바꾸는 조작이 아니라 읽기 전용에서도 막지 않는다
    element, info, failure = locate_target(page, args, state, "hover", should_wait=True,
                                           should_guard_mutating=False)
    if failure:
        return failure
    failure = perform_on_target(page, args, "hover", info,
                                lambda: element.hover(timeout=target_wait_seconds(args) * 1000))
    if failure:
        return failure
    page.wait_for_timeout(300)   # 툴팁·메뉴가 그려질 틈
    payload = done_payload("hover", page)
    payload.update({"target": info, "next": "web text  # 펼쳐진 메뉴·툴팁 글자를 읽는다"})
    return payload


ACTION = Action(name="hover", run=execute, options=("selector", "ref", "target_timeout"),
                help="요소 위에 마우스를 올린다 — 툴팁·펼침 메뉴",
                example="web hover --selector '#menu'")
