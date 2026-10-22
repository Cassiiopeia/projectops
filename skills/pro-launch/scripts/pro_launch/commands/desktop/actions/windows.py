"""`desktop windows` — 열린 창 목록 (앞에 있는 것부터). --window 에 넣을 제목을 고르는 용도."""
from __future__ import annotations

from pro_launch.commands.desktop.common import public_window
from pro_launch.registry import Action
from pro_launch.runtime.output import out

# 브라우저 — 페이지 안은 web 이 더 정확하다
BROWSER_APPS = {"chrome.exe", "msedge.exe", "firefox.exe", "whale.exe", "brave.exe",
                "google chrome", "safari", "firefox", "microsoft edge", "arc"}


def execute(args) -> int:
    be = args.backend
    rows = [public_window(w) for w in be.windows()]
    front = next((w for w in rows if w["foreground"]), None)
    payload = {"ok": True, "code": "ok", "platform": be.name, "count": len(rows), "windows": rows,
               "summary": f"{len(rows)} windows" + (f", in front: {front['title'][:60]}" if front else ""),
               "next": "desktop tree --window \"<part of a title>\""}
    if front and (front.get("app") or "").lower() in BROWSER_APPS:
        payload["hint"] = "The window in front is a browser — for the page itself use web find / web click"
    return out(payload)


ACTION = Action(name="windows", needs="nothing", run=execute, options=(), device_use="read",
                help="List open windows, front first (title, app, pid, bounds, elevated)", example="desktop windows")
