"""`web scroll` — 글자·ref 가 보이게, 또는 정한 거리만큼 내린다 (#880).

관리 콘솔은 창이 아니라 안쪽 상자가 스크롤하는 경우가 많다. --by 에서 창이 안 움직이면
가장 큰 스크롤 상자를 골라 그것을 움직이고 무엇을 움직였는지(container) 돌려준다.
"""
from __future__ import annotations

from pro_launch.commands.web.element import locate_target
from pro_launch.commands.web.frames import frame_scope
from pro_launch.registry import Action

# 창 또는 상자를 by 만큼 내린다. selector 가 없고 창이 안 움직이면 가장 큰 스크롤 상자를 쓴다
SCROLL_BY_JS = """(o) => {
  const describe = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '')
    + (typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\\s+/)[0] : '');
  const move = e => { const before = e.scrollTop; e.scrollBy(0, o.by);
    return { before, after: e.scrollTop, max: e.scrollHeight - e.clientHeight }; };
  if (o.container) {
    const box = document.querySelector(o.container);
    if (!box) return { missing: true };
    return { container: o.container, ...move(box) };
  }
  const page = document.scrollingElement || document.documentElement;
  const moved = move(page);
  if (moved.after !== moved.before) return { container: 'window', ...moved };
  const boxes = [...document.querySelectorAll('body *')].filter(e => {
    const s = getComputedStyle(e);
    return /(auto|scroll|overlay)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 1 && e.clientHeight > 0; });
  if (!boxes.length) return { container: 'window', ...moved };
  const biggest = boxes.sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0];
  return { container: describe(biggest), auto_picked: true, ...move(biggest) };
}"""

CENTER_JS = "(e) => { e.scrollIntoView({block: 'center', inline: 'nearest'}); const r = e.getBoundingClientRect(); return {top: Math.round(r.top)}; }"


def _scroll_to_text(scope, args) -> dict:
    locator = scope.get_by_text(args.to)
    if locator.count() == 0:
        return {"ok": False, "code": "text_not_found", "action": "scroll", "to": args.to,
                "error": f"Text '{args.to}' is not in the page document",
                "next": "web text --grep <word>  # check the actual text"}
    position = locator.first.evaluate(CENTER_JS)
    return {"action": "scroll", "to": args.to, "position": position,
            "summary": f"Scrolled '{args.to}' into view", "next": "web shot  # or pick nearby elements with web find"}


def _scroll_by(scope, args) -> dict:
    moved = scope.evaluate(SCROLL_BY_JS, {"by": args.by, "container": args.container})
    if moved.get("missing"):
        return {"ok": False, "code": "container_not_found", "action": "scroll", "container": args.container,
                "error": f"No container matches {args.container}", "next": "web inspect  # see the page structure"}
    has_moved = moved["after"] != moved["before"]
    is_at_end = moved["after"] >= moved["max"] - 1 if args.by > 0 else moved["after"] <= 0
    return {"action": "scroll", "by": args.by, **moved, "moved": has_moved, "at_end": is_at_end,
            "summary": scroll_summary(moved, has_moved, is_at_end),
            "next": "web find  # pick what is newly visible" if (has_moved or is_at_end)
                    else "Specify the scroll container with --container <css>"}


def scroll_summary(moved: dict, has_moved: bool, is_at_end: bool) -> str:
    """움직임 > 한 줄. 안 움직였으면 끝인지 · 스크롤 상자가 아닌지 가른다"""
    if has_moved:
        return f"Moved {moved['container']} by {moved['after'] - moved['before']}px" + (" (reached the end)" if is_at_end else "")
    if is_at_end and moved["max"] > 0:
        return f"{moved['container']} is already at the end"
    return "Did not move (not a scroll container)"


def execute(page, args, state: dict) -> dict:
    scope, failure = frame_scope(page, args, "scroll")
    if failure:
        return failure
    if args.to:
        payload = _scroll_to_text(scope, args)
    elif args.ref is not None:
        element, info, failure = locate_target(page, args, state, "scroll", should_guard_mutating=False)
        if failure:
            return failure
        payload = {"action": "scroll", "target": info, "position": element.evaluate(CENTER_JS),
                   "summary": "Scrolled the element into view", "next": "web shot  # or web click --ref"}
    elif args.by is not None:
        payload = _scroll_by(scope, args)
    else:
        return {"ok": False, "code": "scroll_target_required", "action": "scroll",
                "error": "One of --to, --ref or --by is required", "next": "web scroll --by 600"}
    payload.setdefault("url", page.url)
    return payload


def configure(p) -> None:
    p.add_argument("--to", default=None, help="Bring this text to the middle of the screen")
    p.add_argument("--by", type=int, default=None, help="Scroll down this many px. Negative scrolls up")
    p.add_argument("--container", default=None, help="--by: selector of the scroll container to move (default: the window, or the largest container if the window does not move)")


ACTION = Action(name="scroll", run=execute, configure=configure, options=("ref", "frame"),
                help="Scroll text or a ref into view, or by a set distance (inner containers too)",
                example='web scroll --to "Payment history"')
