"""`desktop click` — ref 로 누른다 (마우스 없이가 기본). 구조가 없는 화면만 --at 0~1 비율."""
from __future__ import annotations

import desktop_input
from app_input import parse_ratio

from pro_launch.commands.desktop.common import pick_window, public_window
from pro_launch.commands.desktop.input_ops import (before_digest, ensure_front, finish, guarded_mouse_click,
                                                   mutating_refusal, press_node, resolve_ref)
from pro_launch.registry import Action
from pro_launch.runtime.output import out


def _click_at(be, args) -> int:
    at = parse_ratio(args.at)
    if not at:
        return out({"ok": False, "code": "bad_ratio",
                    "error": "--at is a 0-1 ratio inside the window (e.g. 0.5,0.8). Pixels are not accepted"})
    window, failure = pick_window(be, args.window)
    if failure:
        return out(failure)
    failure = ensure_front(be, window)
    if failure:
        return out(failure)
    if not args.confirm_mutating:
        # 글자를 모르는 곳을 누르므로 무엇이 바뀔지 판단할 수 없다 — 사람에게 먼저 묻는다
        return out({"ok": False, "code": "mutating_blocked", "reason": "unknown_target",
                    "error": "A ratio click cannot tell what it presses",
                    "ask_user": "I need to click a spot I cannot read as a button. Shall I click it?",
                    "next": f"desktop click --at {args.at} --window \"{window['title'][:40]}\" --confirm-mutating"})
    region = window["bounds"]
    before = before_digest(be, region)
    x, y = desktop_input.ratio_point(region, *at)
    ok, detail, failure = guarded_mouse_click(be, x, y, is_double=args.double)
    if failure:
        return out(failure)
    payload = {"ok": ok, "code": "ok" if ok else "click_failed", "transport": "mouse", "detail": detail,
               "window": public_window(window), "point": [x, y],
               "summary": f"Clicked {args.at} in {window['title'][:40]}" if ok else detail,
               "next": "desktop tree  # read the new screen"}
    return out(finish(be, args, region, before, payload) if ok else payload)


def execute(args) -> int:
    be = args.backend
    if args.at:
        return _click_at(be, args)
    if args.ref is None:
        return out({"ok": False, "code": "target_required", "error": "Needs --ref <n> (from find/tree) or --at x,y",
                    "next": "desktop find --text \"<text>\""})
    window, node, failure = resolve_ref(be, args.ref)
    failure = failure or mutating_refusal(node, args.confirm_mutating) or ensure_front(be, window)
    if failure:
        return out(failure)
    region = window["bounds"]
    before = before_digest(be, region)
    ok, detail, transport, failure = press_node(be, window, node)
    if failure:
        return out(failure)
    payload = {"ok": ok, "code": "ok" if ok else "click_failed", "transport": transport, "detail": detail,
               "element": desktop_input.public_node(node), "window": public_window(window),
               "summary": f"Pressed '{node.get('text')}' ({transport})" if ok else detail,
               "next": "desktop tree  # read the new screen"}
    return out(finish(be, args, region, before, payload) if ok else payload)


def configure(p) -> None:
    p.add_argument("--ref", type=int, default=None, help="number from the last find/tree")
    p.add_argument("--at", default=None, help="0-1 ratio inside the window, only when there is no element")
    p.add_argument("--double", action="store_true", help="--at: double click")


ACTION = Action(name="click", needs="nothing", run=execute, configure=configure,
                options=("window", "shot", "confirm"), device_use="mutate",
                help="Press an element by ref (no mouse when possible); --at only for screens without elements",
                example="desktop click --ref 3 --shot after_next")
