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
                "error": f"'{args.to}' 글자가 화면 문서에 없습니다",
                "next": "web text --grep <낱말>  # 실제 글자를 확인한다"}
    position = locator.first.evaluate(CENTER_JS)
    return {"action": "scroll", "to": args.to, "position": position,
            "summary": f"'{args.to}' 가 보이게 옮겼다", "next": "web shot  # 또는 web find 로 그 주변을 고른다"}


def _scroll_by(scope, args) -> dict:
    moved = scope.evaluate(SCROLL_BY_JS, {"by": args.by, "container": args.container})
    if moved.get("missing"):
        return {"ok": False, "code": "container_not_found", "action": "scroll", "container": args.container,
                "error": f"{args.container} 에 맞는 상자가 없습니다", "next": "web inspect  # 화면 구조를 본다"}
    has_moved = moved["after"] != moved["before"]
    is_at_end = moved["after"] >= moved["max"] - 1 if args.by > 0 else moved["after"] <= 0
    return {"action": "scroll", "by": args.by, **moved, "moved": has_moved, "at_end": is_at_end,
            "summary": scroll_summary(moved, has_moved, is_at_end),
            "next": "web find  # 새로 보이는 것을 고른다" if (has_moved or is_at_end)
                    else "--container <css> 로 스크롤 상자를 지정한다"}


def scroll_summary(moved: dict, has_moved: bool, is_at_end: bool) -> str:
    """움직임 > 한 줄. 안 움직였으면 끝인지 · 스크롤 상자가 아닌지 가른다"""
    if has_moved:
        return f"{moved['container']} 를 {moved['after'] - moved['before']}px 옮겼다" + (" (끝에 닿음)" if is_at_end else "")
    if is_at_end and moved["max"] > 0:
        return f"{moved['container']} 는 이미 끝이다"
    return "움직이지 않았다 (스크롤 상자가 아니다)"


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
                   "summary": "요소가 보이게 옮겼다", "next": "web shot  # 또는 web click --ref"}
    elif args.by is not None:
        payload = _scroll_by(scope, args)
    else:
        return {"ok": False, "code": "scroll_target_required", "action": "scroll",
                "error": "--to · --ref · --by 중 하나가 필요합니다", "next": "web scroll --by 600"}
    payload.setdefault("url", page.url)
    return payload


def configure(p) -> None:
    p.add_argument("--to", default=None, help="이 글자가 화면 가운데 오게")
    p.add_argument("--by", type=int, default=None, help="이만큼(px) 내린다. 음수면 올린다")
    p.add_argument("--container", default=None, help="--by: 움직일 스크롤 상자 선택자 (없으면 창, 창이 안 움직이면 가장 큰 상자)")


ACTION = Action(name="scroll", run=execute, configure=configure, options=("ref", "frame"),
                help="글자·ref 가 보이게, 또는 정한 거리만큼 내린다 (안쪽 상자도)",
                example='web scroll --to "결제 내역"')
