"""`desktop` 입력 동작이 함께 쓰는 순서 — ref 다시 찾기 · 위험 버튼 · 마우스 없이 · 사용자 개입 · 결과 확인 (#985).

누르는 순서
    1) 창이 앞에 없으면 앞으로
    2) 요소가 패턴을 지원하면 마우스 없이 실행     transport: invoke
    3) 아니면 사용자 개입을 확인한 뒤 마우스로     transport: mouse
    4) 화면 비교 → screen_changed, 멈출 때까지 기다린 뒤 --shot
"""
from __future__ import annotations

import desktop_input

from pro_launch.commands.desktop.common import save_shot, screen_digest, settle
from pro_launch.runtime import desktop_state
from pro_launch.runtime.mutating import is_mutating_label

# 누르기에 쓰는 패턴 우선순위 (입력값을 넣는 set_value 는 type 이 쓴다)
PRESS_ACTIONS = ("invoke", "toggle", "select", "expand")
# 백엔드 perform 이 "찾은 요소가 그 요소가 아니다"를 알리는 이유 문구
STALE_REASONS = ("element is gone", "element changed")


def stale_failure(detail: str) -> dict:
    return {"ok": False, "code": "ref_stale", "error": f"The {detail} since find",
            "next": "desktop find --text \"<text>\"  # number the elements again"}


def resolve_ref(be, ref: int) -> tuple[dict | None, dict | None, dict | None]:
    """(창, 노드, 실패 결과). 마지막 tree·find 의 ref 를 지금 창 목록과 맞춘다."""
    snap = desktop_state.load_snapshot()
    nodes = snap.get("nodes") or []
    node = next((n for n in nodes if n.get("ref") == ref), None)
    if node is None:
        return None, None, {"ok": False, "code": "ref_stale" if nodes else "ref_missing",
                            "error": f"ref {ref} is not in the last tree/find result",
                            "next": "desktop find --text \"<text>\"  # number the elements again"}
    saved = snap.get("window") or {}
    window = next((w for w in be.windows() if w["handle"] == saved.get("handle")), None)
    if window is None:
        return None, None, {"ok": False, "code": "ref_stale", "error": "The window of that ref is gone",
                            "next": "desktop windows"}
    return window, node, None


def mutating_refusal(node: dict, is_confirmed: bool) -> dict | None:
    if node.get("mutating") and not is_confirmed:
        return {"ok": False, "code": "mutating_blocked", "element": desktop_input.public_node(node),
                "error": f"'{node.get('text')}' changes something that is hard to undo",
                "ask_user": f"Pressing '{node.get('text')}' will make a change. Shall I press it?",
                "next": f"desktop click --ref {node.get('ref')} --confirm-mutating  # only after the user agrees"}
    if not node.get("enabled", True):
        return {"ok": False, "code": "element_disabled", "element": desktop_input.public_node(node),
                "error": f"'{node.get('text')}' is disabled", "next": "desktop wait --settle, then find again"}
    return None


def named_action_refusal(node: dict, name: str, is_confirmed: bool) -> dict | None:
    """`click --action` — 노드 문구가 아니라 동작 이름으로 판정한다 (배너 본문은 버튼이 아니다)."""
    names = node.get("named_actions") or []
    if name not in names:
        return {"ok": False, "code": "action_not_found", "candidates": names, "element": desktop_input.public_node(node),
                "error": f"'{node.get('text')}' has no action named {name!r}",
                "next": f"desktop click --ref {node.get('ref')} --action \"<one of candidates>\""}
    if is_mutating_label(name, is_desktop=True) and not is_confirmed:
        return {"ok": False, "code": "mutating_blocked", "element": desktop_input.public_node(node), "action": name,
                "error": f"'{name}' on '{node.get('text')}' changes something that is hard to undo",
                "ask_user": f"Pressing '{name}' on '{node.get('text')}' will make a change. Shall I press it?",
                "next": f"desktop click --ref {node.get('ref')} --action \"{name}\" --confirm-mutating  # only after the user agrees"}
    return None


def guarded_mouse_click(be, x: int, y: int, is_double: bool = False) -> tuple[bool, str, dict | None]:
    """사용자가 마우스를 쓰고 있으면 누르지 않고 세션을 멈춘다. (성공, 이유, 실패 결과)"""
    session = desktop_state.my_session() or {}
    if desktop_input.cursor_moved_by_user(session.get("last_cursor"), be.cursor()):
        desktop_state.touch_session(paused=True)
        return False, "user moved the mouse", {
            "ok": False, "code": "user_interrupted", "error": "The user moved the mouse, so I did not click",
            "ask_user": "You moved the mouse while I was working. May I continue?",
            "next": "desktop session resume  # only after the user agrees"}
    ok, detail = be.mouse_click(x, y, is_double=is_double)
    desktop_state.touch_session(last_cursor=[x, y])
    return ok, detail, None


def press_node(be, window: dict, node: dict) -> tuple[bool, str, str, dict | None]:
    """(성공, 이유, transport, 실패 결과). 패턴이 있으면 마우스를 쓰지 않는다."""
    for action in (a for a in PRESS_ACTIONS if a in (node.get("actions") or [])):
        ok, detail = be.perform(window, node, action)
        if detail in STALE_REASONS:
            return False, detail, "invoke", stale_failure(detail)
        if ok:
            desktop_state.touch_session()
            return True, detail, "invoke", None
        # 이 패턴이 실패했다 — 다음 패턴, 그다음 마우스
    ok, detail, failure = guarded_mouse_click(be, *node["center"])
    return ok, detail, "mouse", failure


def keys_target_refusal(be, window: dict) -> dict | None:
    """키를 보내기 전 — 시스템 창(배너·팝업)이 정말 앞에 왔는지. 아니면 키가 사용자가 쓰던 앱으로 간다."""
    if not window.get("overlay"):
        return None
    now = next((w for w in be.windows() if w["handle"] == window["handle"]), None)
    if now and now.get("foreground"):
        return None
    return {"ok": False, "code": "focus_failed", "window": window.get("title"),
            "error": "This system window cannot take keyboard focus, so keys would go to another app",
            "next": "desktop find --window overlay --text \"<button>\"  # press its buttons instead"}


def ensure_front(be, window: dict) -> dict | None:
    if window.get("elevated"):
        return {"ok": False, "code": "elevated_window", "window": window.get("title"),
                "error": "This window runs as administrator; Windows blocks input from this session",
                "ask_user": f"'{window.get('title')}' runs as administrator. Please press it yourself"}
    if window.get("foreground"):
        return None
    ok, detail = be.focus(window)
    return None if ok else {"ok": False, "code": "focus_failed", "error": detail,
                            "next": "Ask the user to click the window once, then retry"}


def finish(be, args, region: list[int] | None, before: str | None, payload: dict) -> dict:
    """화면 변화 · 기다림 · --shot 을 붙인다."""
    changed, waited = settle(be, region, before)
    payload.update(screen_changed=changed, settle_seconds=waited)
    if changed is False:
        payload["hint"] = "Nothing changed on screen — pick another candidate"
    if getattr(args, "shot", None):
        payload["shot"] = save_shot(be, args, region, args.shot)
    return payload


def before_digest(be, region: list[int] | None) -> str | None:
    return screen_digest(be, region)
