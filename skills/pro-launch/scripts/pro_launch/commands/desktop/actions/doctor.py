"""`desktop doctor` — 의존성 · 권한 · 보안 화면 · 입력 세션 상태를 한 번에 본다."""
from __future__ import annotations

from pro_launch.commands.desktop.common import load_backend
from pro_launch.registry import Action
from pro_launch.runtime import desktop_state
from pro_launch.runtime.output import out

# macOS 권한 이름 → 사용자가 켜는 곳 (메뉴 경로)
PERMISSION_PATHS = {
    "accessibility": "System Settings → Privacy & Security → Accessibility → turn on your terminal app",
    "screen_recording": "System Settings → Privacy & Security → Screen & System Audio Recording → turn on your terminal app",
}


def execute(args) -> int:
    be, failure = load_backend()
    holder = desktop_state.current_holder()
    session = {"held_by_me": bool(desktop_state.my_session()), "holder": holder.get("session") if holder else None,
               "purpose": holder.get("purpose") if holder else None}
    if failure:
        return out({**failure, "session": session})
    ready = be.readiness()
    missing = [k for k, granted in (ready.get("permissions") or {}).items() if not granted]
    windows = be.windows()
    payload = {"ok": not missing, "code": "ok" if not missing else "permission_missing", "platform": be.name,
               "readiness": ready, "window_count": len(windows), "session": session,
               "summary": f"{be.name}: {len(windows)} windows" + (f", missing {', '.join(missing)}" if missing else ""),
               "next": "desktop windows" if not missing else None}
    if missing:
        payload["grant"] = {k: PERMISSION_PATHS.get(k, k) for k in missing}
        payload["ask_user"] = "Please grant " + " and ".join(missing) + " to your terminal app, then restart it"
    return out(payload)


ACTION = Action(name="doctor", needs="nothing", run=execute, options=(), device_use="none",
                help="Check packages, OS permissions, security prompts and the input session", example="desktop doctor")
