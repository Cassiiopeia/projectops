"""`web click` — press exactly one chosen element and return what changed."""
from __future__ import annotations


from pro_launch.commands.web.session import safe_title, settle
from pro_launch.commands.web.frames import child_frames
from pro_launch.commands.web.element import (is_timeout_error, locate_target, not_actionable_failure,
                                             outcome_wait_seconds, target_wait_seconds)
from pro_launch.registry import Action

# What covers the element's center point — checks whether a fixed header, footer or overlay intercepts the click (#879).
# Scroll it into view first if off screen; a cover that is the element itself, a descendant or an ancestor does not count
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


# Fingerprint for spotting a change on the same screen: element count, open dialog count, visible text length (#1048)
PAGE_FINGERPRINT_JS = """() => [document.querySelectorAll('*').length,
  document.querySelectorAll('dialog[open]').length, (document.body ? document.body.innerText : '').length].join(':')"""


# Max child frames to fingerprint (keeps pages with many ad iframes from slowing down)
MAXIMUM_FINGERPRINTED_FRAMES = 10
# Placeholder for a frame that could not be read
UNREADABLE_FRAME_MARK = "?"


# Watcher counting whether the press actually reached the page: capture phase of the element's window (#1048)
# Observed: in a long-running shared browser a tab can drop all CDP mouse/key input > do not silently report "no change"
INPUT_PROBE_EVENT_TYPES = "['pointerdown', 'mousedown', 'click']"
# Internal value passed inside recovery: number of events that arrived (not in the response)
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
    """Install the watcher. False if it cannot (e.g. mid-navigation) — then delivery is not judged."""
    try:
        element.evaluate(ARM_INPUT_PROBE_JS)
        return True
    except Exception:
        return False


def read_delivered_input_count(element) -> int | None:
    """Number of input events that arrived, then remove the watcher (success or failure). None if unreadable after navigation or recreation."""
    try:
        return element.evaluate(READ_INPUT_PROBE_JS)
    except Exception:
        return None


def input_not_delivered_failure(page, args, info: dict) -> dict:
    """Press finished but no event reached the page > suggest --dom-click or a browser restart"""
    return {"ok": False, "code": "input_not_delivered", "action": "click", "clicked": info, "url": page.url,
            "error": "The click was sent, but no pointer or click event reached the page",
            "hint": "This tab is dropping browser input (seen in a long-running shared browser), "
                    "or the page cancels every pointer event before its own listeners and nothing changed. "
                    "--dom-click calls the element's click() directly. "
                    "Restarting the browser (web close, then web open) also clears it, but closes its other tabs: "
                    "check web tab list first",
            "next": f"{covered_retry_command(args)}  # click through the DOM instead of browser input"}


def read_page_fingerprint(page) -> str | None:
    """None if unreadable (e.g. mid-navigation)"""
    try:
        return page.evaluate(PAGE_FINGERPRINT_JS)
    except Exception:
        return None


def read_frames_fingerprint(page) -> str:
    """URL + fingerprint per child frame (#1132)
    Step changes inside a cross-origin login iframe do not show in the top-level fingerprint > read the same fingerprint per frame
    """
    return "|".join(f"{frame.url}={read_page_fingerprint(frame) or UNREADABLE_FRAME_MARK}"
                    for frame in child_frames(page)[:MAXIMUM_FINGERPRINTED_FRAMES])


def covering_element(element, should_center: bool) -> str | None:
    """Description of what covers the element (e.g. header#top.sticky "Admin"). None if not covered or unreadable."""
    try:
        return element.evaluate(COVERING_ELEMENT_JS, should_center)
    except Exception:
        return None


def covered_retry_command(args) -> str:
    """One-line command to press the covered element again with --dom-click"""
    target = f"--ref {args.ref}" if args.ref is not None else f"--selector \"{args.selector}\""
    frame = f" --frame \"{args.frame}\"" if getattr(args, "frame", None) else ""
    return f"web click {target}{frame} --dom-click"


def click_with_cover_recovery(page, element, args, info: dict) -> tuple[dict, dict | None]:
    """Press: if covered, scroll it to the center and check again > if still covered and --dom-click, DOM click().

    (recovery record, failure result). If still covered at timeout, element_not_actionable with covered_by and a --dom-click hint.
    """
    recovery: dict = {}
    url_before_click = page.url
    covered_by = covering_element(element, should_center=False)
    if covered_by:
        recovery = {"covered_by": covered_by, "scrolled_to_center": True}
        covered_by = covering_element(element, should_center=True)
        recovery["still_covered"] = bool(covered_by)
    if covered_by and args.dom_click:
        # Call the element's click() directly, bypassing the cover — may differ from a human click, so only when asked
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
        # If the page navigates after the press and the element disappears, it looks like a timeout: navigated means success (#1074)
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
    # _web_click judges after the screen settles (avoids misjudging pages that swallow events)
    if is_probe_armed and page.url == url_before_click:
        recovery[DELIVERED_INPUT_COUNT_KEY] = read_delivered_input_count(element)
    return recovery, None


def is_input_dropped(recovery: dict, changed: bool = False, content_changed: bool = False) -> bool:
    """Not delivered only when there were 0 events and the screen is unchanged (an unreadable None is not judged)"""
    return recovery.get(DELIVERED_INPUT_COUNT_KEY) == 0 and not changed and not content_changed


def dom_click_if_input_dropped(element, args, recovery: dict) -> None:
    """If --dom-click was given and input did not arrive, try once more with the element's click() (only when asked)"""
    if args.dom_click and is_input_dropped(recovery):
        element.evaluate("(e) => e.click()")
        recovery.pop(DELIVERED_INPUT_COUNT_KEY, None)
        recovery.update({"input_not_delivered": True, "dom_click": True})


def _web_click(page, args, state: dict) -> dict:
    """Press exactly one chosen element and return what was pressed and what changed."""
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
            # Without an expectation, wait only briefly — SPAs change the URL late
            try:
                page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass  # A late load signal is fine; fall through to the short wait below
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
        # Could be an in-place change like a checkbox or expander — do not call it a failure; ask for a check
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
