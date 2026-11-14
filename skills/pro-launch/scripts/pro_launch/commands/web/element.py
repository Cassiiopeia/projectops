"""Pick the one element to act on — shared by click, type, select, check, press, hover and download.

Order: check the target (--ref, --selector) > find (candidates if not found) > fail immediately if disabled (#888) > read-only session block
If the action itself times out, perform_on_target turns it into element_not_actionable with candidates (#888)
"""
from __future__ import annotations

from pro_launch.commands.web.candidates import attach_candidates
from pro_launch.commands.web.frames import frame_scope
from pro_launch.commands.web.targets import REF_ATTR, is_mutating_target

# Default wait for the target element (seconds) — only this much is spent when a guess misses (#888, was 10)
TARGET_WAIT_SECONDS = 4
# Default wait (seconds) for the result after clicking (--expect-*, download start, loading)
OUTCOME_WAIT_SECONDS = 10


# Element description + visible / disabled (password field values are not included). Disabled checks all three: disabled attribute, aria-disabled, inside a disabled fieldset
DESCRIBE_STATE_JS = """(e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
  return { tag: e.tagName.toLowerCase(), role: e.getAttribute('role'), type: e.getAttribute('type'),
    text: (e.type === 'password' ? '' : (e.innerText || e.value || '')).replace(/\\s+/g, ' ').trim().slice(0, 120),
    aria: e.getAttribute('aria-label') || e.getAttribute('title'), href: e.getAttribute('href'),
    name: e.getAttribute('name'), aria_label: e.getAttribute('aria-label'), placeholder: e.getAttribute('placeholder'),
    visible: r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none',
    disabled: !!e.disabled || e.getAttribute('aria-disabled') === 'true' || !!e.closest('fieldset[disabled]') }; }"""


def target_wait_seconds(args) -> int:
    """Time to wait for the target element. The --timeout value if given"""
    timeout = getattr(args, "timeout", None)
    return TARGET_WAIT_SECONDS if timeout is None else timeout


def outcome_wait_seconds(args) -> int:
    """Time to wait for the result after clicking. The --timeout value if given"""
    timeout = getattr(args, "timeout", None)
    return OUTCOME_WAIT_SECONDS if timeout is None else timeout


def target_selector(args) -> str | None:
    """Element with that number if --ref is given, otherwise --selector."""
    if getattr(args, "ref", None) is not None:
        return f'[{REF_ATTR}="{args.ref}"]'
    return getattr(args, "selector", None)


def target_label(info: dict) -> str:
    return (info.get("text") or info.get("aria") or info.get("tag") or "")[:40]


def locate_target(page, args, state: dict, action: str, *, should_wait: bool = False,
                  should_guard_mutating: bool = True):
    """(element, description, failure result). If there is a failure result, element is None.

    should_wait: if the selector isn't there yet, wait up to the target wait time for it to attach (screens that render inputs late).
    Refs are not waited for — if missing, the screen changed and the element must be picked again.
    """
    selector = target_selector(args)
    if not selector:
        return None, None, {"ok": False, "code": "target_required", "action": action,
                            "error": "--ref or --selector is required",
                            "next": "web inspect  # get numbered input and button candidates, then pick one with --ref"}
    # With --frame, search only inside that iframe (#877). Candidates are picked there too
    scope, failure = frame_scope(page, args, action)
    if failure:
        return None, None, failure
    locator = scope.locator(selector)
    if locator.count() == 0 and should_wait and args.ref is None:
        try:
            locator.first.wait_for(state="attached", timeout=target_wait_seconds(args) * 1000)
        except Exception:
            pass  # if it doesn't attach in time, the count() == 0 path below reports the failure
    if locator.count() == 0:
        if args.ref is not None:
            return None, None, attach_candidates(
                {"ok": False, "code": "ref_stale", "action": action, "url": page.url,
                 "error": f"ref {args.ref} is not on the screen (gone after navigation or re-render)",
                 "hint": "Refs do not survive a reload or re-render. If the control only exists while its row is hovered, "
                         "run web hover on the row first, then web find",
                 "next": "web find  # pick again from the current screen"}, scope, None, action)
        return None, None, attach_candidates(
            {"ok": False, "code": "selector_not_found", "action": action, "url": page.url,
             "error": f"No element matches {args.selector}", "next": "web find --text <text>"},
            scope, args.selector, action)
    element = locator.first
    info = element.evaluate(DESCRIBE_STATE_JS)
    # The element actually picked and the match count — exposes comma selectors that hit the wrong first element yet returned ok (#931)
    info["matches"] = locator.count()
    if args.ref is not None:
        info["ref"] = args.ref
    if getattr(args, "frame", None):
        info["frame"] = args.frame
    # Visible but disabled won't help even if we wait out the timeout — report right away (#888)
    if info.get("visible") and info.get("disabled"):
        return None, info, {"ok": False, "code": "element_disabled", "action": action, "target": info,
                            "url": page.url,
                            "error": f"'{target_label(info)}' is disabled",
                            "next": "web inspect  # check for inputs or checkboxes that must be filled first"}
    if (should_guard_mutating and state.get("readonly") and is_mutating_target(info)
            and not getattr(args, "confirm_mutating", False)):
        return None, info, {"ok": False, "code": "mutating_blocked", "action": action, "clicked": None,
                            "target": info, "url": page.url,
                            "error": f"Read-only session: did not touch '{target_label(info)}'",
                            "next": "If it really must be done, tell the user what will change, get approval, then add --confirm-mutating"}
    return element, info, None


def is_timeout_error(error: Exception) -> bool:
    """Is it a Playwright wait timeout (TimeoutError or 'Timeout …ms exceeded')."""
    return "Timeout" in type(error).__name__ or "timeout" in str(error).lower()


def not_actionable_failure(page, args, action: str, info: dict | None, error: Exception) -> dict:
    """The element exists but couldn't be acted on within the wait (hidden, covered, moving) — include candidates."""
    # Only the first line of the Playwright message — the call log after it may contain input values (passwords)
    detail = str(error).strip().splitlines()[0][:200] if str(error).strip() else type(error).__name__
    is_secret_input = bool(getattr(args, "text_env", None) or getattr(args, "cred", None))
    if is_secret_input and getattr(args, "text", None):
        detail = detail.replace(args.text, "***")
    label = target_label(info or {}) or (getattr(args, "selector", None) or "")
    failure = {"ok": False, "code": "element_not_actionable", "action": action, "target": info, "url": page.url,
               "error": f"Could not act on '{label}' within {target_wait_seconds(args)}s (hidden, covered or moving)",
               "detail": detail, "next": "web inspect  # pick a visible input or button again by ref"}
    selector = None if getattr(args, "ref", None) is not None else getattr(args, "selector", None)
    scope = frame_scope(page, args, action)[0] or page
    return attach_candidates(failure, scope, selector, action)


def perform_on_target(page, args, action: str, info: dict | None, operation) -> dict | None:
    """Perform one action. Returns a failure result with candidates on wait timeout, None on success. Other exceptions propagate."""
    try:
        operation()
    except Exception as error:
        if not is_timeout_error(error):
            raise
        return not_actionable_failure(page, args, action, info, error)
    return None


def attach_match_warning(payload: dict) -> None:
    """If the action's target matched several selector elements, add matches and warning at the top level (refs are single, so not applicable)"""
    for key in ("target", "clicked"):
        info = payload.get(key)
        if isinstance(info, dict) and (info.get("matches") or 0) > 1 and "ref" not in info:
            payload["matches"] = info["matches"]
            payload.setdefault("warning", "multiple_matches")
            payload.setdefault("warning_detail", (
                f"Selector matched {info['matches']} elements and used the first ({info.get('tag')} "
                f"'{target_label(info)}') — if that is not the intended element, pick one with --ref from web find or web inspect"))
            return
