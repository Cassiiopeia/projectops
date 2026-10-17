"""--frame 으로 iframe 안을 다룬다 — find · click · type · assert 등 대상을 고르는 동작이 함께 쓴다 (#877).

로그인 폼이 교차 출처 iframe 안이면 page.locator 는 그 안을 못 본다.
찾는 순서: 프레임 이름 > iframe 선택자 > 주소 일부. 못 찾으면 지금 페이지의 프레임 목록을 돌려준다.
"""
from __future__ import annotations

# 실패·안내에 싣는 프레임 수
MAXIMUM_LISTED_FRAMES = 10


def child_frames(page) -> list:
    """최상위를 뺀 프레임들. 못 읽으면 빈 목록."""
    try:
        main = page.main_frame
        return [frame for frame in page.frames if frame != main]
    except Exception:
        return []


def describe_frames(page) -> list[dict]:
    """자식 프레임 목록 (name · url) — --frame 에 그대로 넣을 수 있는 값이다."""
    described = []
    for frame in child_frames(page)[:MAXIMUM_LISTED_FRAMES]:
        try:
            described.append({"name": frame.name or None, "url": frame.url})
        except Exception:
            continue
    return described


def _frame_by_selector(page, spec: str):
    """iframe 요소 선택자 → 그 안의 문서. 선택자가 아니거나 iframe 이 아니면 None."""
    try:
        locator = page.locator(spec)
        if locator.count() == 0:
            return None
        handle = locator.first.element_handle(timeout=2000)
        return handle.content_frame() if handle else None
    except Exception:
        return None


def find_frame(page, spec: str):
    """--frame 값 하나로 프레임을 고른다: 이름 > iframe 선택자 > 주소 일부. 없으면 None."""
    frames = child_frames(page)
    for frame in frames:
        if frame.name and frame.name == spec:
            return frame
    by_selector = _frame_by_selector(page, spec)
    if by_selector is not None:
        return by_selector
    for frame in frames:
        if spec in (frame.url or ""):
            return frame
    return None


def frame_scope(page, args, action: str):
    """(찾을 곳, 실패 결과). --frame 이 없으면 페이지 자체."""
    spec = getattr(args, "frame", None)
    if not spec:
        return page, None
    frame = find_frame(page, spec)
    if frame is None:
        return None, {"ok": False, "code": "frame_not_found", "action": action, "url": page.url,
                      "error": f"--frame '{spec}' 에 맞는 iframe 이 없습니다",
                      "frames": describe_frames(page),
                      "next": "frames 의 name 이나 url 일부를 --frame 에 넣는다"}
    return frame, None


def frames_hint(page) -> dict:
    """대상을 못 찾았을 때 붙일 안내 — 자식 프레임이 있으면 목록과 --frame 쓰는 법."""
    frames = describe_frames(page)
    if not frames:
        return {}
    return {"frames": frames,
            "hint": "이 페이지에 iframe 이 있다. 대상이 그 안이면 --frame <이름|iframe 선택자|주소 일부> 를 붙인다"}
