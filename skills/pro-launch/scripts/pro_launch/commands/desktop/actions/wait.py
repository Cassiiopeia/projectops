"""`desktop wait` — 글자가 나타날 때까지 · 사라질 때까지 · 화면이 멈출 때까지 기다린다."""
from __future__ import annotations

import time

import node_match

from pro_launch.commands.desktop.actions.tree import remember
from pro_launch.commands.desktop.common import listed_nodes, pick_window, screen_digest, settle, windows_to_search
from pro_launch.registry import Action
from pro_launch.runtime.output import out

POLL_SECONDS = 0.5


# 결과에 싣는 일치 노드 수
MAX_MATCHES = 10


def _matches(be, args, window) -> list[dict]:
    nodes = be.nodes(window, args.max_nodes, args.depth) or []
    return node_match.find_nodes(listed_nodes(nodes), "text", args.text)[0]


def _first_with_text(be, args) -> tuple[dict | None, list[dict]]:
    """(글자가 있는 창, 일치 노드). 없으면 첫 창과 빈 목록 — 창이 하나도 없으면 (None, [])."""
    windows, _ = windows_to_search(be, args.window)
    for window in windows:
        found = _matches(be, args, window)
        if found:
            return window, found
    return (windows[0] if windows else None), []


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
        window, found = _first_with_text(be, args)
        # 창 자체가 닫혔으면 글자도 사라진 것이다 (닫힌 배너 · 설치 창)
        if (window is not None or args.gone) and bool(found) != args.gone:
            payload = {"ok": True, "code": "ok", "waited_seconds": round(time.monotonic() - started, 2),
                       "window": window["title"] if window else None,
                       "summary": f"{args.text!r} {'is gone' if args.gone else 'appeared'}", "next": "desktop find"}
            if found:
                # ref 를 바로 남긴다 — 알림 배너는 약 5초면 사라져 find 를 한 번 더 부를 틈이 없다
                payload["matches"] = remember(window, found)[:MAX_MATCHES]
                payload["next"] = "desktop click --ref <n>  # refs are ready, no find needed"
            return out(payload)
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
