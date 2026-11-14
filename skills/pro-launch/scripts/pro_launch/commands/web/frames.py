"""Handle iframe contents via --frame — shared by target-picking actions such as find, click, type and assert (#877).

If a login form is inside a cross-origin iframe, page.locator can't see inside.
Lookup order: frame name > iframe selector > part of the URL. If not found, return the current page's frame list.
"""
from __future__ import annotations

# Number of frames included in failures and hints
MAXIMUM_LISTED_FRAMES = 10


def child_frames(page) -> list:
    """Frames other than the top one. Empty list if unreadable."""
    try:
        main = page.main_frame
        return [frame for frame in page.frames if frame != main]
    except Exception:
        return []


def describe_frames(page) -> list[dict]:
    """Child frame list (name, url) — values usable as-is for --frame."""
    described = []
    for frame in child_frames(page)[:MAXIMUM_LISTED_FRAMES]:
        try:
            described.append({"name": frame.name or None, "url": frame.url})
        except Exception:
            continue
    return described


def _frame_by_selector(page, spec: str):
    """iframe element selector → its document. None if not a selector or not an iframe."""
    try:
        locator = page.locator(spec)
        if locator.count() == 0:
            return None
        handle = locator.first.element_handle(timeout=2000)
        return handle.content_frame() if handle else None
    except Exception:
        return None


def find_frame(page, spec: str):
    """Pick a frame from one --frame value: name > iframe selector > part of the URL. None if not found."""
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
    """(where to search, failure result). The page itself if --frame is absent."""
    spec = getattr(args, "frame", None)
    if not spec:
        return page, None
    frame = find_frame(page, spec)
    if frame is None:
        return None, {"ok": False, "code": "frame_not_found", "action": action, "url": page.url,
                      "error": f"No iframe matches --frame '{spec}'",
                      "frames": describe_frames(page),
                      "next": "Pass a name or part of a url from frames to --frame"}
    return frame, None


def frames_hint(page) -> dict:
    """Hint added when the target isn't found — lists child frames and how to use --frame, if any."""
    frames = describe_frames(page)
    if not frames:
        return {}
    return {"frames": frames,
            "hint": "This page has iframes. If the target is inside one, add --frame <name|iframe selector|part of url>"}
