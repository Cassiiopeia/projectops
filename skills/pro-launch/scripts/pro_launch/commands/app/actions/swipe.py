"""`app swipe` — swipe the screen."""
from __future__ import annotations


import app_input

from pro_launch.commands.app.gestures import backend_for, before_shot, gesture_result
from pro_launch.registry import Action
from pro_launch.runtime.output import out


def _app_swipe(args) -> int:
    """Swipe. --dir up|down|left|right or --from/--to ratio coordinates."""
    direction = _requested_direction(args)
    if direction:
        start, end = app_input.SWIPE_DIRS[direction]
    else:
        start = app_input.parse_ratio(getattr(args, "frm", None))
        end = app_input.parse_ratio(getattr(args, "to", None))
        if not (start and end):
            return out({"ok": False, "code": "swipe_target_required",
                        "error": "Needs --dir or --from/--to (0–1 ratio, e.g. 0.5,0.8)",
                        "next": "app swipe --dir up  # up · down · left · right, or --from 0.5,0.8 --to 0.5,0.2"})
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    before = before_shot(args, be, dev_id)
    ms = getattr(args, "ms", 300) or 300
    ok, detail = be.swipe_ratio(dev_id, start, end, ms)
    return gesture_result(args, be, dev_id, before, ok, detail, "swipe_failed",
                           f"Swipe {direction or f'{start}→{end}'}")


def _requested_direction(args) -> str | None:
    """--dir (or --direction), else a bare direction word (`app swipe up`)"""
    if getattr(args, "dir", None):
        return args.dir
    word = getattr(args, "session_verb", None)
    return word if word in app_input.SWIPE_DIRS else None


def configure(p) -> None:
    p.add_argument("--dir", "--direction", dest="dir", choices=sorted(app_input.SWIPE_DIRS), default=None, help="swipe: direction")
    p.add_argument("--from", dest="frm", default=None, help="swipe: start ratio coordinate (e.g. 0.5,0.8)")
    p.add_argument("--to", default=None, help="swipe: end ratio coordinate")
    p.add_argument("--ms", type=int, default=300, help="swipe: duration (ms)")


ACTION = Action(name="swipe", device_use="mutate", run=_app_swipe, configure=configure)
