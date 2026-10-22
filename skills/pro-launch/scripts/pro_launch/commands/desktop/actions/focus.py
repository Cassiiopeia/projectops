"""`desktop focus` — 창을 앞으로 가져온다 (최소화돼 있으면 되살린다)."""
from __future__ import annotations

from pro_launch.commands.desktop.common import pick_window, public_window
from pro_launch.commands.desktop.input_ops import ensure_front
from pro_launch.registry import Action
from pro_launch.runtime import desktop_state
from pro_launch.runtime.output import out


def execute(args) -> int:
    be = args.backend
    if not args.window:
        return out({"ok": False, "code": "target_required", "error": "Needs --window", "next": "desktop windows"})
    window, failure = pick_window(be, args.window)
    if failure:
        return out(failure)
    failure = ensure_front(be, window)
    if failure:
        return out(failure)
    desktop_state.touch_session()
    return out({"ok": True, "code": "ok", "window": public_window(window),
                "summary": f"{window['title'][:50]} is in front", "next": "desktop tree"})


ACTION = Action(name="focus", needs="nothing", run=execute, options=("window",), device_use="mutate",
                help="Bring a window to the front", example="desktop focus --window \"Setup\"")
