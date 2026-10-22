"""`desktop press` — 앞에 있는 창에 키를 보낸다 (Enter · Tab · Esc · 방향키 · ctrl+a …)."""
from __future__ import annotations

from pro_launch.commands.desktop.common import pick_window
from pro_launch.commands.desktop.input_ops import before_digest, ensure_front, finish
from pro_launch.registry import Action
from pro_launch.runtime import desktop_state
from pro_launch.runtime.output import out

# 되돌리기 어려운 결과가 바로 나는 키 — 확인 없이 보내지 않는다
RISKY_COMBOS = {("alt", "f4"), ("ctrl", "w"), ("cmd", "q"), ("cmd", "w"), ("ctrl", "s"), ("cmd", "s"),
                ("shift", "delete")}


def execute(args) -> int:
    be = args.backend
    mods = [m.strip().lower() for m in (args.mods or "").split(",") if m.strip()]
    key = args.key.lower()
    if any((m, key) in RISKY_COMBOS for m in mods) and not args.confirm_mutating:
        return out({"ok": False, "code": "mutating_blocked", "error": f"{'+'.join([*mods, key])} closes or saves something",
                    "ask_user": f"Pressing {'+'.join([*mods, key])} may close or save something. Shall I?",
                    "next": f"desktop press --key {key} --mods {','.join(mods)} --confirm-mutating"})
    window, failure = pick_window(be, args.window)
    if failure:
        return out(failure)
    failure = ensure_front(be, window)
    if failure:
        return out(failure)
    region = window["bounds"]
    before = before_digest(be, region)
    ok, detail = be.press(key, mods)
    if ok:
        desktop_state.touch_session()
    payload = {"ok": ok, "code": "ok" if ok else "press_failed", "detail": detail, "window": window["title"],
               "summary": f"Pressed {detail}" if ok else detail, "next": "desktop tree"}
    return out(finish(be, args, region, before, payload) if ok else payload)


def configure(p) -> None:
    p.add_argument("--key", required=True, help="enter, tab, esc, space, up/down/left/right, f1-f12, or one letter")
    p.add_argument("--mods", default=None, help="comma list: ctrl, shift, alt, win (cmd on macOS)")


ACTION = Action(name="press", needs="nothing", run=execute, configure=configure,
                options=("window", "shot", "confirm"), device_use="mutate",
                help="Send a key to the window in front", example="desktop press --key enter")
