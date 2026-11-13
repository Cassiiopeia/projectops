"""`web click` — 고른 요소 하나만 누르고 무엇이 바뀌었는지 돌려준다."""
from __future__ import annotations


from pro_launch.commands.web.session import safe_title, settle
from pro_launch.commands.web.frames import child_frames
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


# 같은 화면에서 무언가 바뀌었는지 보는 지문: 요소 수, 열린 대화상자 수, 보이는 글자 수 (#1048)
PAGE_FINGERPRINT_JS = """() => [document.querySelectorAll('*').length,
  document.querySelectorAll('dialog[open]').length, (document.body ? document.body.innerText : '').length].join(':')"""


# 지문을 읽는 자식 프레임 수 상한 (광고 iframe 이 많은 페이지에서 느려지지 않게)
MAXIMUM_FINGERPRINTED_FRAMES = 10
# 못 읽은 프레임 자리 표시
UNREADABLE_FRAME_MARK = "?"


# 누름이 실제로 페이지에 닿았는지 세는 감시: 요소가 속한 창의 capture 단계 (#1048)
# 오래 띄운 공유 브라우저에서 탭이 CDP 마우스·키 입력을 통째로 버리는 상태가 실측됨 > 조용히 "변화 없음"이 되지 않게
INPUT_PROBE_EVENT_TYPES = "['pointerdown', 'mousedown', 'click']"
# recovery 안의 내부 전달값: 닿은 이벤트 수 (응답에는 안 나감)
DELIVERED_INPUT_COUNT_KEY = "_delivered_input_count"
ARM_INPUT_PROBE_JS = """(e) => {
  const w = e.ownerDocument.defaultView;
  const count = () => { w.__projectopsInputCount = (w.__projectopsInputCount || 0) + 1; };
  w.__projectopsInputCount = 0;
  %s.forEach((t) => w.addEventListener(t, count, true));
  w.__projectopsInputProbeOff = () => %s.forEach((t) => w.removeEventListener(t, count, true));
}""" % (INPUT_PROBE_EVENT_TYPES, INPUT_PROBE_EVENT_TYPES)
READ_INPUT_PROBE_JS = """(e) => {
  const w = e.ownerDocument.defaultView;
  const delivered = w.__projectopsInputCount;
  if (w.__projectopsInputProbeOff) w.__projectopsInputProbeOff();
  delete w.__projectopsInputCount; delete w.__projectopsInputProbeOff;
  return typeof delivered === 'number' ? delivered : null;
}"""


def arm_input_probe(element) -> bool:
    """감시 설치. 못 하면 False (이동 중 등) — 그때는 닿았는지 판정하지 않는다."""
    try:
        element.evaluate(ARM_INPUT_PROBE_JS)
        return True
    except Exception:
        return False


def read_delivered_input_count(element) -> int | None:
    """닿은 입력 이벤트 수, 감시 해제 (성공·실패 공통). 이동·재생성으로 못 읽으면 None."""
    try:
        return element.evaluate(READ_INPUT_PROBE_JS)
    except Exception:
        return None


def input_not_delivered_failure(page, args, info: dict) -> dict:
    """누르기는 끝났는데 페이지에 이벤트가 하나도 안 닿음 > --dom-click 또는 브라우저 재시작 안내"""
    return {"ok": False, "code": "input_not_delivered", "action": "click", "clicked": info, "url": page.url,
            "error": "The click was sent, but no pointer or click event reached the page",
            "hint": "This tab is dropping browser input (seen in a long-running shared browser), "
                    "or the page cancels every pointer event before its own listeners and nothing changed. "
                    "--dom-click calls the element's click() directly. "
                    "Restarting the browser (web close, then web open) also clears it, but closes its other tabs: "
                    "check web tab list first",
            "next": f"{covered_retry_command(args)}  # click through the DOM instead of browser input"}


def read_page_fingerprint(page) -> str | None:
    """못 읽으면 None (이동 중 등)"""
    try:
        return page.evaluate(PAGE_FINGERPRINT_JS)
    except Exception:
        return None


def read_frames_fingerprint(page) -> str:
    """자식 프레임별 주소 + 지문 (#1132)
    교차 출처 로그인 iframe 안 단계 전환은 최상위 지문에 안 잡힘 > 프레임마다 같은 지문을 읽는다
    """
    return "|".join(f"{frame.url}={read_page_fingerprint(frame) or UNREADABLE_FRAME_MARK}"
                    for frame in child_frames(page)[:MAXIMUM_FINGERPRINTED_FRAMES])


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
    url_before_click = page.url
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
    is_probe_armed = arm_input_probe(element)
    try:
        element.click(timeout=target_wait_seconds(args) * 1000)
    except Exception as error:
        if is_probe_armed:
            read_delivered_input_count(element)
        if not is_timeout_error(error):
            raise
        # 누른 뒤 페이지가 넘어가 요소가 사라지면 시간 초과처럼 보임: 이동했으면 성공 (#1074)
        if page.url != url_before_click:
            recovery["navigated_during_click"] = True
            return recovery, None
        failure = not_actionable_failure(page, args, "click", info, error)
        cover = covered_by or ("intercepts pointer events" in str(error) and covering_element(element, True))
        if cover:
            failure.update({"reason": "covered", "covered_by": cover,
                            "hint": f"'{cover}' intercepts the click (sticky header or overlay). "
                                    "If it need not match a real user click, --dom-click calls the element's click() directly",
                            "next": f"{covered_retry_command(args)}  # click without going through the cover"})
        return recovery, failure
    # 판정은 화면이 가라앉은 뒤 _web_click 이 한다 (이벤트를 삼키는 페이지에서 오판 방지)
    if is_probe_armed and page.url == url_before_click:
        recovery[DELIVERED_INPUT_COUNT_KEY] = read_delivered_input_count(element)
    return recovery, None


def is_input_dropped(recovery: dict, changed: bool = False, content_changed: bool = False) -> bool:
    """이벤트 0건이고 화면도 그대로일 때만 안 닿은 것 (못 읽은 None 은 판정 안 함)"""
    return recovery.get(DELIVERED_INPUT_COUNT_KEY) == 0 and not changed and not content_changed


def dom_click_if_input_dropped(element, args, recovery: dict) -> None:
    """--dom-click 을 줬고 입력이 안 닿았으면 요소의 click() 으로 한 번 더 (명시했을 때만)"""
    if args.dom_click and is_input_dropped(recovery):
        element.evaluate("(e) => e.click()")
        recovery.pop(DELIVERED_INPUT_COUNT_KEY, None)
        recovery.update({"input_not_delivered": True, "dom_click": True})


def _web_click(page, args, state: dict) -> dict:
    """고른 요소 하나만 누르고, 무엇을 눌렀고 무엇이 바뀌었는지 돌려준다."""
    el, info, failure = locate_target(page, args, state, "click")
    if failure:
        return failure
    before_url, before_title = page.url, safe_title(page)
    before_fingerprint = read_page_fingerprint(page)
    before_frames_fingerprint = read_frames_fingerprint(page)
    recovery, failure = click_with_cover_recovery(page, el, args, info)
    if failure:
        return failure
    dom_click_if_input_dropped(el, args, recovery)
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
                pass  # 로드 신호가 늦어도 아래 짧은 대기로 넘어간다
            page.wait_for_timeout(800)
    except Exception:
        if is_input_dropped(recovery):
            return input_not_delivered_failure(page, args, info)
        return {"ok": False, "code": "expect_not_met", "action": "click", "clicked": info,
                "expected": args.expect_url or args.expect_text,
                "before": {"url": before_url, "title": before_title},
                "url": page.url, "title": safe_title(page),
                "error": f"Clicked, but the expected {'URL' if waited == 'url' else 'text'} did not appear within {outcome_seconds}s",
                "next": "web text  # read the current screen; if the wrong thing was clicked, pick again with web find"}
    settle(page, state, outcome_seconds)
    after_url, after_title = page.url, safe_title(page)
    changed = after_url != before_url or after_title != before_title
    after_fingerprint = read_page_fingerprint(page)
    frame_content_changed = read_frames_fingerprint(page) != before_frames_fingerprint
    content_changed = (before_fingerprint is None or after_fingerprint is None or before_fingerprint != after_fingerprint
                       or frame_content_changed)
    if is_input_dropped(recovery, changed, content_changed):
        return input_not_delivered_failure(page, args, info)
    recovery.pop(DELIVERED_INPUT_COUNT_KEY, None)
    outcome_text = ("URL or title changed" if changed else
                    "URL and title unchanged, content inside an iframe changed"
                    if frame_content_changed and before_fingerprint == after_fingerprint else
                    "URL and title unchanged, page content changed" if content_changed else
                    "nothing visible changed")
    payload = {"action": "click", "clicked": info, "changed": changed, "content_changed": content_changed,
               "frame_content_changed": frame_content_changed, "before": {"url": before_url, "title": before_title},
               "url": after_url, "title": after_title,
               "summary": f"Clicked '{(info.get('text') or info.get('aria') or info.get('tag'))[:40]}' → "
                          + outcome_text}
    if recovery:
        payload["recovery"] = recovery
    if not changed and not (args.expect_url or args.expect_text):
        # 체크박스·펼치기처럼 제자리에서 바뀌는 것일 수도 있다 — 실패로 단정하지 않고 확인을 시킨다
        payload["next"] = ("Check with web text / web assert that it did what you intended. If not, pick again with web find"
                           if content_changed else
                           "The click may not have reached the element: check with web text, then try --dom-click or web script")
    else:
        payload["next"] = "web text  # read the changed screen"
    return payload


def configure(p) -> None:
    p.add_argument("--expect-url", dest="expect_url", default=None,
                   help="After clicking, wait until the URL contains this text. Fails otherwise")
    p.add_argument("--expect-text", dest="expect_text", default=None,
                   help="After clicking, wait until this text is visible. Fails otherwise")
    p.add_argument("--dom-click", dest="dom_click", action="store_true",
                   help="If a sticky header or overlay covers it, or the tab drops browser input, "
                        "call the element's click() directly (#879, #1048)")


ACTION = Action(name="click", run=_web_click, configure=configure,
                options=("ref", "selector", "target_timeout", "confirm_mutating", "frame", "capture_requests"),
                help="Click exactly one chosen element and report what changed",
                example="web click --ref 3 --expect-url /home")
