"""`web wait` — wait until conditions hold: URL · text · disappearance · element (#880).

Waits for 2FA approval on another device, upload completion, save toasts or URL changes instead of fixed sleeps or repeated text.
**All** given conditions must hold to finish. It does not navigate on an approval screen — navigating cancels the pending approval.
"""
from __future__ import annotations

import time

from pro_launch.commands.web.frames import frame_scope
from pro_launch.commands.web.session import safe_title
from pro_launch.commands.web.targets import SELECTOR_SYNTAX_HINT, is_selector_syntax_error
from pro_launch.commands.web.url_match import url_without_query
from pro_launch.registry import Action

# Interval for rechecking conditions (ms)
POLL_INTERVAL_MILLISECONDS = 500
# Default wait cap (seconds) — time for a person to approve on another device
DEFAULT_WAIT_SECONDS = 120

# All visible text (innerText omits hidden text)
VISIBLE_TEXT_JS = "() => document.body ? document.body.innerText : ''"
# Lower bound for --reload-every (seconds) — so the server is not hammered · load cap for one reload (seconds)
MINIMUM_RELOAD_SECONDS = 5
RELOAD_LOAD_SECONDS = 15


class InvalidSelectorError(Exception):
    """Selector syntax error: fail immediately rather than 'not visible yet'"""


def reload_page(page) -> bool:
    """One reload. On failure (slow load · mid-navigation) check again next round > whether it succeeded"""
    try:
        page.reload(wait_until="domcontentloaded", timeout=RELOAD_LOAD_SECONDS * 1000)
        return True
    except Exception:
        return False


def wait_conditions(args) -> dict:
    """Collect only the given conditions. name → expected value"""
    named = {"url_contains": args.url_contains, "text": args.text, "gone": args.gone, "selector": args.selector}
    return {name: value for name, value in named.items() if value}


def unmet_conditions(conditions: dict, url: str, visible_text: str, is_selector_visible: bool) -> list[str]:
    """Names of conditions not yet met. Empty list means done"""
    unmet = []
    needle = conditions.get("url_contains")
    if needle and needle not in url_without_query(url, needle):
        unmet.append("url_contains")
    if "text" in conditions and conditions["text"] not in visible_text:
        unmet.append("text")
    if "gone" in conditions and conditions["gone"] in visible_text:
        unmet.append("gone")
    if "selector" in conditions and not is_selector_visible:
        unmet.append("selector")
    return unmet


def _read_snapshot(page, scope, conditions: dict) -> tuple[str, str, bool]:
    """(URL, visible text, whether the selector is visible). Empty values if unreadable mid-navigation — check again next round"""
    try:
        visible_text = scope.evaluate(VISIBLE_TEXT_JS) if ("text" in conditions or "gone" in conditions) else ""
    except Exception:
        visible_text = ""
    is_selector_visible = False
    if "selector" in conditions:
        try:
            locator = scope.locator(conditions["selector"])
            is_selector_visible = locator.count() > 0 and locator.first.is_visible()
        except Exception as error:
            if is_selector_syntax_error(str(error)):
                raise InvalidSelectorError(str(error)[:200]) from error
            is_selector_visible = False   # e.g. context destroyed mid-navigation — check again next round
    return page.url, visible_text or "", is_selector_visible


def execute(page, args, state: dict) -> dict:
    conditions = wait_conditions(args)
    if not conditions:
        return {"ok": False, "code": "nothing_to_wait_for", "action": "wait",
                "error": "Give at least one of --url-contains · --text · --gone · --selector",
                "next": 'web wait --text "Saved" --timeout 30'}
    scope, failure = frame_scope(page, args, "wait")
    if failure:
        return failure
    reload_seconds = getattr(args, "reload_every", None)
    if reload_seconds is not None and reload_seconds < MINIMUM_RELOAD_SECONDS:
        return {"ok": False, "code": "reload_too_frequent", "action": "wait", "reload_every": reload_seconds,
                "error": f"--reload-every must be at least {MINIMUM_RELOAD_SECONDS}s",
                "next": f"web wait --text <text> --reload-every 15 --timeout {args.timeout}"}
    started = time.monotonic()
    deadline = started + args.timeout
    last_reload = started
    reload_count = 0
    # Check one last time even past the deadline — so a match right at the boundary is not missed
    while True:
        try:
            url, visible_text, is_selector_visible = _read_snapshot(page, scope, conditions)
        except InvalidSelectorError as error:
            return {"ok": False, "code": "bad_selector", "action": "wait", "conditions": conditions,
                    "error": f"Selector syntax error: {error}", "hint": SELECTOR_SYNTAX_HINT,
                    "next": "web inspect  # get element candidates and selectors, then fix --selector"}
        unmet = unmet_conditions(conditions, url, visible_text, is_selector_visible)
        waited_seconds = round(time.monotonic() - started, 1)
        if not unmet:
            return {"action": "wait", "conditions": conditions, "waited_seconds": waited_seconds,
                    "reloads": reload_count, "url": url, "title": safe_title(page),
                    "summary": f"Conditions met after {waited_seconds}s", "next": "web text  # read the changed screen"}
        if time.monotonic() >= deadline:
            return {"ok": False, "code": "wait_timeout", "action": "wait", "conditions": conditions,
                    "unmet": unmet, "waited_seconds": waited_seconds, "reloads": reload_count,
                    "url": url, "title": safe_title(page),
                    "error": f"Conditions not met within {args.timeout}s: {', '.join(unmet)}",
                    "next": "web text  # look at the current screen. If it is waiting for approval, do not navigate; call web wait again"}
        page.wait_for_timeout(POLL_INTERVAL_MILLISECONDS)
        # Screens that only change on reload (PR state · deploy result) — reload at the set interval (#930)
        if reload_seconds and time.monotonic() - last_reload >= reload_seconds and time.monotonic() < deadline:
            reload_count += reload_page(page)
            last_reload = time.monotonic()
            if args.frame:
                # A reload also gives the iframe a new document — pick it again (next round if not rendered yet)
                scope = frame_scope(page, args, "wait")[0] or scope


def configure(p) -> None:
    p.add_argument("--url-contains", dest="url_contains", default=None, help="Until the URL (scheme, host and path; the ?query and #fragment only if this text has ? or #) contains this text")
    p.add_argument("--gone", default=None, help="Until this text disappears from the screen (loading or uploading messages)")
    p.add_argument("--timeout", type=int, default=DEFAULT_WAIT_SECONDS,
                   help=f"Wait limit (seconds, default {DEFAULT_WAIT_SECONDS})")
    p.add_argument("--reload-every", dest="reload_every", type=int, default=None,
                   help=f"Reload every N seconds while waiting (min {MINIMUM_RELOAD_SECONDS}) — for screens that change only on reload")


ACTION = Action(name="wait", run=execute, configure=configure, options=("text", "selector", "frame"),
                help="Wait until the URL, text, gone and element conditions are all met (every condition given)",
                example='web wait --text "Merged" --reload-every 15 --timeout 180')
