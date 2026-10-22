"""`desktop wait` — 글자가 나타날 때까지 · 사라질 때까지 · 화면이 멈출 때까지 기다린다."""
from __future__ import annotations

import time

import node_match

from pro_launch.commands.desktop.common import listed_nodes, pick_window, screen_digest, settle
from pro_launch.registry import Action
from pro_launch.runtime.output import out

POLL_SECONDS = 0.5


def _present(be, args, window) -> bool:
    nodes = be.nodes(window, args.max_nodes, args.depth) or []
    return bool(node_match.find_nodes(listed_nodes(nodes), "text", args.text)[0])


def execute(args) -> int:
    be = args.backend
    if not args.text and not args.settle:
        return out({"ok": False, "code": "target_required", "error": "Needs --text (with or without --gone) or --settle"})
    started = time.monotonic()
    if args.settle:
        window, failure = pick_window(be, args.window)
        if failure:
            return out(failure)
        changed, waited = settle(be, window["bounds"], screen_digest(be, window["bounds"]))
        return out({"ok": True, "code": "ok", "changed": changed, "waited_seconds": waited,
                    "summary": "Screen settled", "next": "desktop tree"})
    while time.monotonic() - started < args.timeout:
        # 창이 새로 뜨거나 닫힐 수 있어 매번 다시 고른다 (설치 마법사의 다음 단계 창)
        window, _ = pick_window(be, args.window)
        if window is not None and _present(be, args, window) != args.gone:
            return out({"ok": True, "code": "ok", "waited_seconds": round(time.monotonic() - started, 2),
                        "window": window["title"],
                        "summary": f"{args.text!r} {'is gone' if args.gone else 'appeared'}", "next": "desktop find"})
        time.sleep(POLL_SECONDS)
    return out({"ok": False, "code": "wait_timeout", "error": f"{args.text!r} did not {'go away' if args.gone else 'appear'} "
                f"within {args.timeout}s", "next": "desktop windows  # see what is on screen now"})


def configure(p) -> None:
    p.add_argument("--text", default=None, help="text to wait for")
    p.add_argument("--gone", action="store_true", help="wait until --text disappears")
    p.add_argument("--settle", action="store_true", help="wait until the window stops changing (max 3s)")


ACTION = Action(name="wait", needs="nothing", run=execute, configure=configure,
                options=("window", "timeout", "limits"), device_use="read",
                help="Wait for text to appear or go away, or for the window to settle",
                example="desktop wait --text \"Completed\" --timeout 120")
