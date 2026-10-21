"""`web viewport` — 폭을 바꿔 찍는다."""
from __future__ import annotations

import re
from pathlib import Path

from pro_launch.registry import Action
from pro_launch.runtime.browser import write_state
from pro_launch.runtime.output import out


# 폭을 바꿔 찍을 때 쓰는 이름. 숫자를 외우지 않게 한다.
VIEWPORT_PRESETS = {"mobile": (390, 844), "tablet": (820, 1180), "desktop": (1280, 800)}


def _web_viewport(args, state: dict, state_f: Path) -> int:
    """폭을 바꿔 찍는다. 값은 상태 파일에 남아 다음 연결에도 걸린다."""
    if args.clear:
        state["viewport"] = None
        write_state(state_f, state)
        return out({"action": "viewport", "viewport": None,
                    "summary": "Viewport cleared (follows the window size)"})
    preset = args.preset or ""
    # --width/--height 는 자주 짐작해서 쓰는 형태 — 390x844 와 같은 뜻이다 (#931)
    if args.width or args.height:
        if not (args.width and args.height):
            return out({"ok": False, "code": "bad_viewport", "viewport": None,
                        "error": "--width and --height must be given together",
                        "hint": "web viewport --width 1280 --height 800 (or --preset 1280x800)"})
        preset = f"{args.width}x{args.height}"
    if preset in VIEWPORT_PRESETS:
        w, h = VIEWPORT_PRESETS[preset]
    else:
        m = re.fullmatch(r"(\d{2,5})x(\d{2,5})", preset)
        if not m:
            return out({"ok": False, "code": "bad_viewport", "viewport": None,
                        "error": f"Unknown viewport '{preset}'",
                        "hint": f"{' · '.join(VIEWPORT_PRESETS)} or widthxheight such as 390x844"})
        w, h = int(m.group(1)), int(m.group(2))
    state["viewport"] = [w, h]
    write_state(state_f, state)
    return out({"action": "viewport", "viewport": [w, h],
                "summary": f"Viewport {w}x{h}",
                "next": "web shot  # captures at this width (redraw with web goto if needed)"})


def configure(p) -> None:
    p.add_argument("--preset", default=None, help="viewport: mobile · tablet · desktop or 390x844")
    p.add_argument("--width", type=int, default=None, help="viewport: width (px) — with --height (same as --preset 1280x800)")
    p.add_argument("--height", type=int, default=None, help="viewport: height (px)")


ACTION = Action(name="viewport", needs="state_offline", run=_web_viewport, configure=configure,
                options=("clear",), help="Change the width — applies from the next connection",
                example="web viewport --preset mobile")
