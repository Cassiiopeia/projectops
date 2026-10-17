"""`web click` — 고른 요소 하나만 누르고 무엇이 바뀌었는지 돌려준다."""
from __future__ import annotations


from pro_launch.commands.web.session import safe_title, settle
from pro_launch.commands.web.element import (is_timeout_error, locate_target, not_actionable_failure,
                                             outcome_wait_seconds, target_wait_seconds)
from pro_launch.registry import Action

# 요소 가운데 점을 덮은 것 — 고정 머리글·바닥글·오버레이가 클릭을 가로채는지 본다 (#879).
# 화면 밖이면 먼저 보이게 하고, 덮은 것이 자기 자신·자손·조상이면 가려진 것이 아니다
COVERING_ELEMENT_JS = """(e, shouldCenter) => {
  if (shouldCenter) e.scrollIntoView({block: 'center', inline: 'center'});
  else { const r0 = e.getBoundingClientRect();
    if (r0.bottom < 0 || r0.top > innerHeight || r0.right < 0 || r0.left > innerWidth) e.scrollIntoView({block: 'center'}); }
  const r = e.getBoundingClientRect();
  const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  if (!top || top === e || e.contains(top) || top.contains(e)) return null;
  const cls = typeof top.className === 'string' && top.className.trim() ? '.' + top.className.trim().split(/\\s+/)[0] : '';
  const words = (top.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 40);
  return top.tagName.toLowerCase() + (top.id ? '#' + top.id : '') + cls + (words ? ' "' + words + '"' : '');
}"""


def covering_element(element, should_center: bool) -> str | None:
    """요소를 덮은 것의 설명 (예: header#top.sticky "관리자"). 안 덮였거나 못 읽으면 None."""
    try:
        return element.evaluate(COVERING_ELEMENT_JS, should_center)
    except Exception:
        return None


def covered_retry_command(args) -> str:
    """덮인 요소를 --dom-click 으로 다시 누르는 명령 한 줄"""
    target = f"--ref {args.ref}" if args.ref is not None else f"--selector \"{args.selector}\""
    frame = f" --frame \"{args.frame}\"" if getattr(args, "frame", None) else ""
    return f"web click {target}{frame} --dom-click"


def click_with_cover_recovery(page, element, args, info: dict) -> tuple[dict, dict | None]:
    """누른다: 덮였으면 가운데로 스크롤해 다시 보고 > 그래도 덮였고 --dom-click 이면 DOM click().

    (복구 기록, 실패 결과). 덮인 채 시간이 다 되면 covered_by 와 --dom-click 안내를 실은 element_not_actionable.
    """
    recovery: dict = {}
    covered_by = covering_element(element, should_center=False)
    if covered_by:
        recovery = {"covered_by": covered_by, "scrolled_to_center": True}
        covered_by = covering_element(element, should_center=True)
        recovery["still_covered"] = bool(covered_by)
    if covered_by and args.dom_click:
        # 덮은 것을 거치지 않고 요소의 click() 을 바로 부른다 — 사람 클릭과 다를 수 있어 명시할 때만
        element.evaluate("(e) => e.click()")
        recovery["dom_click"] = True
        return recovery, None
    try:
        element.click(timeout=target_wait_seconds(args) * 1000)
    except Exception as error:
        if not is_timeout_error(error):
            raise
        failure = not_actionable_failure(page, args, "click", info, error)
        cover = covered_by or ("intercepts pointer events" in str(error) and covering_element(element, True))
        if cover:
            failure.update({"reason": "covered", "covered_by": cover,
                            "hint": f"'{cover}' 이 클릭을 가로챈다 (고정 머리글·오버레이). "
                                    "사람 클릭과 같지 않아도 되면 --dom-click 으로 요소의 click() 을 바로 부른다",
                            "next": f"{covered_retry_command(args)}  # 덮은 것을 거치지 않고 누른다"})
        return recovery, failure
    return recovery, None


def _web_click(page, args, state: dict) -> dict:
    """고른 요소 하나만 누르고, 무엇을 눌렀고 무엇이 바뀌었는지 돌려준다."""
    el, info, failure = locate_target(page, args, state, "click")
    if failure:
        return failure
    before_url, before_title = page.url, safe_title(page)
    recovery, failure = click_with_cover_recovery(page, el, args, info)
    if failure:
        return failure
    outcome_seconds = outcome_wait_seconds(args)
    waited = None
    try:
        if args.expect_url:
            waited = "url"
            page.wait_for_url(lambda u: args.expect_url in u, timeout=outcome_seconds * 1000)
        elif args.expect_text:
            waited = "text"
            page.get_by_text(args.expect_text).first.wait_for(state="visible", timeout=outcome_seconds * 1000)
        else:
            # 기대를 안 줬으면 짧게만 기다린다 — SPA 는 주소가 늦게 바뀐다
            try:
                page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass
            page.wait_for_timeout(800)
    except Exception:
        return {"ok": False, "code": "expect_not_met", "action": "click", "clicked": info,
                "expected": args.expect_url or args.expect_text,
                "before": {"url": before_url, "title": before_title},
                "url": page.url, "title": safe_title(page),
                "error": f"눌렀지만 기대한 {'주소' if waited == 'url' else '글자'}가 {outcome_seconds}초 안에 나오지 않았습니다",
                "next": "web text  # 지금 화면을 읽고, 엉뚱한 것을 눌렀으면 web find 로 다시 고른다"}
    settle(page, state, outcome_seconds)
    after_url, after_title = page.url, safe_title(page)
    changed = after_url != before_url or after_title != before_title
    payload = {"action": "click", "clicked": info, "changed": changed,
               "before": {"url": before_url, "title": before_title},
               "url": after_url, "title": after_title,
               "summary": f"'{(info.get('text') or info.get('aria') or info.get('tag'))[:40]}' 클릭 → "
                          + ("주소·제목이 바뀌었다" if changed else "주소·제목 그대로")}
    if recovery:
        payload["recovery"] = recovery
    if not changed and not (args.expect_url or args.expect_text):
        # 체크박스·펼치기처럼 제자리에서 바뀌는 것일 수도 있다 — 실패로 단정하지 않고 확인을 시킨다
        payload["next"] = "의도한 결과가 맞는지 web text / web assert 로 확인한다. 아니면 web find 로 다시 고른다"
    else:
        payload["next"] = "web text  # 바뀐 화면을 읽는다"
    return payload


def configure(p) -> None:
    p.add_argument("--expect-url", dest="expect_url", default=None,
                   help="누른 뒤 주소에 이 글자가 들어올 때까지 기다린다. 안 오면 실패")
    p.add_argument("--expect-text", dest="expect_text", default=None,
                   help="누른 뒤 이 글자가 보일 때까지 기다린다. 안 오면 실패")
    p.add_argument("--dom-click", dest="dom_click", action="store_true",
                   help="고정 머리글·오버레이가 덮고 있으면 요소의 click() 을 바로 부른다 (#879)")


ACTION = Action(name="click", run=_web_click, configure=configure,
                options=("ref", "selector", "target_timeout", "confirm_mutating", "frame"),
                help="고른 요소 하나만 누르고 무엇이 바뀌었는지 돌려준다",
                example="web click --ref 3 --expect-url /home")
