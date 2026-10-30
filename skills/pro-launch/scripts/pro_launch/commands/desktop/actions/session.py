"""`desktop session start|stop|status|resume` — 이 컴퓨터의 키보드·마우스를 쓸 차례를 잡고 놓는다.

컴퓨터 전체에 하나뿐이다. 입력하지 않은 채 10분이 지나면 풀린다. 세션이 끝나면 훅이 놓는다.
"""
from __future__ import annotations

from pro_launch.commands.desktop.common import load_backend
from pro_launch.commands.desktop.input_ops import user_input_check
from pro_launch.registry import Action
from pro_launch.runtime import desktop_state
from pro_launch.runtime.output import out

START_WARNING = ("This session will now use this computer's keyboard and mouse. "
                 "Moving the mouse or typing pauses it.")
# 키 입력 감지를 못 쓰는 환경 — 마우스만 본다고 알린다 (#985)
START_WARNING_MOUSE_ONLY = ("This session will now use this computer's keyboard and mouse. "
                            "Moving the mouse pauses it (typing is not detected here).")


def keyboard_check() -> dict:
    """세션 시작 결과에 싣는 감지 범위 — 못 읽으면 is_available False 로 알리고 막지는 않는다."""
    be, failure = load_backend()
    if failure:
        return {"is_available": False, "kind": None}
    _, is_available = user_input_check(be)
    return {"is_available": is_available, "kind": be.user_input_kind if is_available else None}


def execute(args) -> int:
    try:
        if args.op == "start":
            got, record = desktop_state.start_session(args.purpose)
            if not got:
                return out({"ok": False, "code": "desktop_busy", "holder": record.get("session"),
                            "purpose": record.get("purpose"),
                            "error": "Another session is using this computer's keyboard and mouse",
                            "next": "desktop session status  # wait, or ask the user"})
            check = keyboard_check()
            warning = START_WARNING if check["is_available"] else START_WARNING_MOUSE_ONLY
            return out({"ok": True, "code": "ok", "session": record, "warning": warning,
                        "tell_user": warning, "keyboard_check": check, "idle_expiry_minutes": desktop_state.SESSION_IDLE_SECONDS // 60,
                        "summary": "Input session started", "next": "desktop find --text \"<button text>\""})
        if args.op == "stop":
            released = desktop_state.stop_session()
            return out({"ok": True, "code": "ok", "released": released,
                        "summary": "Input session stopped" if released else "This session held no input session",
                        "next": None})
        if args.op == "resume":
            if not desktop_state.my_session():
                return out({"ok": False, "code": "desktop_session_required",
                            "error": "This session holds no input session", "next": "desktop session start"})
            desktop_state.touch_session(paused=False, paused_by=None, last_cursor=None)
            return out({"ok": True, "code": "ok", "summary": "Input session resumed", "next": None})
        holder = desktop_state.current_holder()
        return out({"ok": True, "code": "ok", "held_by_me": bool(desktop_state.my_session()),
                    "holder": holder, "summary": f"held by {holder['session']}" if holder else "free", "next": None})
    except desktop_state.DesktopLockBusy as e:
        return out({"ok": False, "code": "desktop_state_busy", "error": str(e), "next": "call again shortly"})


def configure(p) -> None:
    p.add_argument("op", choices=("start", "stop", "status", "resume"))
    p.add_argument("--purpose", default=None, help="start: why (shown to other sessions), e.g. \"#985 installer\"")


ACTION = Action(name="session", needs="nothing", run=execute, configure=configure, options=(), device_use="none",
                help="Take or release this computer's keyboard and mouse (start · stop · status · resume)",
                example="desktop session start --purpose \"#985 installer\"")
