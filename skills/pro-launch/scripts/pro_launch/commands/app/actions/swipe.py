"""`app swipe` — 화면을 민다."""
from __future__ import annotations


import app_input

from pro_launch.commands.app.gestures import backend_for, before_shot, gesture_result
from pro_launch.registry import Action
from pro_launch.runtime.output import out


def _app_swipe(args) -> int:
    """스와이프. --dir up|down|left|right 또는 --from/--to 비율 좌표."""
    if getattr(args, "dir", None):
        start, end = app_input.SWIPE_DIRS[args.dir]
    else:
        start = app_input.parse_ratio(getattr(args, "frm", None))
        end = app_input.parse_ratio(getattr(args, "to", None))
        if not (start and end):
            return out({"ok": False, "code": "swipe_target_required",
                        "error": "--dir 또는 --from/--to (0~1 비율, 예: 0.5,0.8) 가 필요하다"})
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    before = before_shot(args, be, dev_id)
    ms = getattr(args, "ms", 300) or 300
    ok, detail = be.swipe_ratio(dev_id, start, end, ms)
    return gesture_result(args, be, dev_id, before, ok, detail, "swipe_failed",
                           f"스와이프 {args.dir or f'{start}→{end}'}")


def configure(p) -> None:
    p.add_argument("--dir", choices=sorted(app_input.SWIPE_DIRS), default=None, help="swipe: 방향")
    p.add_argument("--from", dest="frm", default=None, help="swipe: 시작 비율 좌표 (예: 0.5,0.8)")
    p.add_argument("--to", default=None, help="swipe: 끝 비율 좌표")
    p.add_argument("--ms", type=int, default=300, help="swipe: 걸리는 시간(ms)")


ACTION = Action(name="swipe", run=_app_swipe, configure=configure)
