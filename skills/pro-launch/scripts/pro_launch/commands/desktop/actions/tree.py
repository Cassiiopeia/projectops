"""`desktop tree` · `desktop find` — 창의 요소를 번호(ref)와 함께 읽는다. 누를 때는 그 번호를 쓴다."""
from __future__ import annotations

import time

import desktop_input
import node_match

from pro_launch.commands.desktop.common import listed_nodes, pick_window, public_window
from pro_launch.registry import Action
from pro_launch.runtime import desktop_state
from pro_launch.runtime.output import out

# 결과에 싣는 요소 수 상한 — 넘으면 find 로 좁히라고 안내한다
MAX_LISTED = 150


def read_nodes(args) -> tuple[dict | None, list[dict] | None, dict | None, float]:
    """(창, 보여 줄 노드, 실패 결과, 읽은 초)."""
    be = args.backend
    window, failure = pick_window(be, args.window)
    if failure:
        return None, None, failure, 0.0
    started = time.monotonic()
    nodes = be.nodes(window, max(1, args.max_nodes), max(1, args.depth))
    elapsed = round(time.monotonic() - started, 3)
    if nodes is None:
        return window, None, {"ok": False, "code": "tree_unavailable", "window": public_window(window),
                              "error": "Could not read this window's structure",
                              "next": "desktop shot --window <same>  # then click --at with a 0-1 ratio"}, elapsed
    return window, listed_nodes(nodes), None, elapsed


def _remember(window: dict, nodes: list[dict]) -> list[dict]:
    """번호를 붙여 상태 파일에 적고, 결과용 모양을 돌려준다."""
    numbered = desktop_input.assign_refs(nodes)
    desktop_state.save_snapshot(public_window(window), numbered)
    return [desktop_input.public_node(n) for n in numbered]


def tree(args) -> int:
    window, nodes, failure, elapsed = read_nodes(args)
    if failure:
        return out(failure)
    elements = _remember(window, nodes)
    cut = len(elements) > MAX_LISTED
    return out({"ok": True, "code": "ok", "platform": args.backend.name, "window": public_window(window),
                "count": len(elements), "elements": elements[:MAX_LISTED], "truncated": cut,
                "elapsed_seconds": elapsed,
                "summary": f"{len(elements)} elements in {window['title'][:50]}" + (" (cut — use find)" if cut else ""),
                "next": "desktop click --ref <n>" if not cut else "desktop find --text \"<text>\""})


def find(args) -> int:
    field, value = next(((f, getattr(args, f"sel_{f}")) for f in ("text", "id", "desc")
                         if getattr(args, f"sel_{f}", None)), (None, None))
    if not field and not args.role:
        return out({"ok": False, "code": "target_required", "error": "Needs one of --text · --id · --desc · --role",
                    "next": "desktop tree  # see every element"})
    window, nodes, failure, elapsed = read_nodes(args)
    if failure:
        return out(failure)
    if args.role:
        nodes = [n for n in nodes if n["role"] == args.role.lower()]
    found = node_match.find_nodes(nodes, field, value)[0] if field else nodes
    if not found:
        return out({"ok": False, "code": "not_found", "window": public_window(window),
                    "candidates": node_match.candidate_values(nodes, field or "text"),
                    "error": f"No element matches {field}={value!r}" if field else f"No {args.role} elements",
                    "next": "desktop find --text \"<one of candidates>\""})
    elements = _remember(window, found)
    return out({"ok": True, "code": "ok", "platform": args.backend.name, "window": public_window(window),
                "count": len(elements), "items": elements[:MAX_LISTED], "elapsed_seconds": elapsed,
                "summary": f"{len(elements)} candidates", "next": "desktop click --ref <n>  # pick by number"})


ACTION = Action(name="tree", needs="nothing", run=tree, options=("window", "limits"), device_use="read",
                help="Read a window's elements with ref numbers", example="desktop tree --window \"Setup\"")
