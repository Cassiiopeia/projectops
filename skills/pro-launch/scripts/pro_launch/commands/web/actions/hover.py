"""`web hover` — move the mouse over an element (tooltips, dropdown menus, #892)."""
from __future__ import annotations


from pro_launch.commands.web.element import locate_target, perform_on_target, target_wait_seconds
from pro_launch.commands.web.session import done_payload
from pro_launch.registry import Action


def execute(page, args, state: dict) -> dict:
    # Only hovers — not a changing action, so read-only sessions allow it
    element, info, failure = locate_target(page, args, state, "hover", should_wait=True,
                                           should_guard_mutating=False)
    if failure:
        return failure
    failure = perform_on_target(page, args, "hover", info,
                                lambda: element.hover(timeout=target_wait_seconds(args) * 1000))
    if failure:
        return failure
    page.wait_for_timeout(300)   # Time for the tooltip or menu to render
    payload = done_payload("hover", page)
    payload.update({"target": info, "next": "web text  # read the opened menu or tooltip text"})
    return payload


ACTION = Action(name="hover", run=execute, options=("selector", "ref", "target_timeout", "frame"),
                help="Hover over an element — tooltips and dropdown menus",
                example="web hover --selector '#menu'")
