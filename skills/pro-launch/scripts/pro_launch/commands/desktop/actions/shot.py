"""`desktop shot` — 창 · 영역 · 주 화면을 찍는다 (WebP, 긴 변 1200px)."""
from __future__ import annotations

from pro_launch.commands.desktop.common import pick_window, public_window, save_shot
from pro_launch.registry import Action
from pro_launch.runtime.output import out
from pro_launch.runtime.shots import add_shot_args


def _region(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    try:
        x1, y1, x2, y2 = (int(v) for v in raw.split(","))
    except ValueError:
        return None
    return [x1, y1, x2, y2] if x2 > x1 and y2 > y1 else None


def execute(args) -> int:
    be = args.backend
    region = _region(args.region)
    if args.region and region is None:
        return out({"ok": False, "code": "bad_region", "error": "--region is x1,y1,x2,y2 in screen pixels"})
    window = None
    if region is None and not args.screen:
        window, failure = pick_window(be, args.window)
        if failure:
            return out(failure)
        region = window["bounds"]
    path = save_shot(be, args, region, args.out)
    if not path:
        return out({"ok": False, "code": "capture_failed", "error": "Could not capture the screen",
                    "next": "desktop doctor  # macOS needs Screen Recording permission"})
    return out({"ok": True, "code": "ok", "file": path, "region": region,
                "window": public_window(window) if window else None,
                "summary": f"Captured {path}", "next": "Read the image only if text (tree · find) is not enough"})


def configure(p) -> None:
    p.add_argument("--out", default=None, help="file name or path (default: timestamp in SHOT_DIR)")
    p.add_argument("--region", default=None, help="x1,y1,x2,y2 screen pixels instead of a window")
    p.add_argument("--screen", action="store_true", help="the whole main screen instead of a window")
    add_shot_args(p)


ACTION = Action(name="shot", needs="nothing", run=execute, configure=configure, options=("window",),
                device_use="read", help="Capture a window, a region or the main screen", example="desktop shot --window \"Setup\" --out 01_setup")
