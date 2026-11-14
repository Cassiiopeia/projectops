"""`web` — drive the browser directly (#586).

The agent picks its next move from screenshots, so operation is split across many CLI calls.
Instead of a resident daemon, this uses **CDP reconnect**.

    open  → start a standalone process with --remote-debugging-port and write the port to the state file
    after → attach to that browser with connect_over_cdp and detach again (session and cookies persist)

⚠️ Some things only live while attached — console hook, viewport, response overrides, dialog handling. They vanish when the connection drops
(#625, observed). So they are written to the state file and **re-applied on every attach** (`session.web_connect`).

Each action is one module in `actions/`. This file gives each action a subparser (the shared options it uses + its own options),
prepares only what the action needs (read state, attach browser) and calls it. Adding an action does not touch this file.
"""
from __future__ import annotations

import argparse
import os
import time

from pro_launch.commands.web import actions as _actions
from pro_launch.commands.web.element import attach_match_warning
from pro_launch.commands.web.options import ALWAYS_OPTIONS, SHARED_OPTIONS, timeout_failure
from pro_launch.commands.web.request_capture import RequestCapture
from pro_launch.commands.web.saved_values import read_saved_values
from pro_launch.commands.web.session import DIALOG_EVENT_KEY, web_connect
from pro_launch.commands.web.tabs import REPORTED_POPUPS_KEY, attach_reload_notice, drift_warning, mark_tab, opened_tabs, reload_notice
from pro_launch.commands.web.targets import SELECTOR_SYNTAX_HINT, is_selector_syntax_error
from pro_launch.commands.web.watchdog import HUNG_MARK_KEY, Watchdog, deadline_seconds, set_watched_browser
from pro_launch.registry import Command, action_usage_lines, add_action_parsers, discover_actions
from pro_launch.runtime import browser_profiles
from pro_launch.runtime.browser import read_state, update_state_for_browser, write_state
from pro_launch.runtime.context import project_root
from pro_launch.runtime.creds import cred_field, with_login_policy
from pro_launch.runtime.output import out, set_area, set_target

ACTIONS = discover_actions(_actions)


def configure(p) -> None:
    # Per-action subparsers — `web <action> --help` shows only the options that action uses (#896)
    add_action_parsers(p, ACTIONS, SHARED_OPTIONS, always=ALWAYS_OPTIONS)
    p.formatter_class = argparse.RawDescriptionHelpFormatter
    p.description = "Drive the browser, one action per call — options per action: web <action> --help"
    p.epilog = "Options per action:\n" + "\n".join(action_usage_lines(p))


def _resolve_secret_text(args) -> tuple[str | None, dict | None]:
    """Pull the input value from --text-env or --cred into args.text. (secret, failure result)

    --text-env: environment variable > otherwise a value saved with web value / clipboard --save-env (#930)
    """
    if getattr(args, "text_env", None):
        value = os.environ.get(args.text_env)
        if value is None:
            value = read_saved_values(project_root(args)).get(args.text_env)
        if value is None:
            return None, {"ok": False, "code": "env_not_set",
                          "error": f"Environment variable {args.text_env} is empty (not in saved values either)",
                          "hint": f'Prefix the same command with {args.text_env}="..." or save it with web value --save-env {args.text_env}'}
        args.text = value
        return args.text, None
    if getattr(args, "cred", None):
        # Type saved login info — the value stays out of the command line and the logs
        value, err = cred_field(args.cred, getattr(args, "cred_field", None))
        if err:
            return None, err
        args.text = value
        return value, None
    return None, None


def apply_profile_choice(args, root) -> dict | None:
    """open --profile <name|repo> / --need kind:name > profile memory. Returns a failure response if none can be chosen."""
    wanted, needs = getattr(args, "profile", None), getattr(args, "need", None) or []
    if needs and not wanted:
        wanted = browser_profiles.profile_with_marks(root, needs)
        if wanted is None:
            return {"ok": False, "code": "no_matching_profile", "needs": needs,
                    "error": f"No browser profile has {', '.join(needs)} recorded",
                    "next": "After logging in, record it with web profile mark --kind login --name <provider> (web profile list)"}
    if wanted is None:
        return None
    if wanted != browser_profiles.REPO_PROFILE_NAME and not browser_profiles.is_valid_profile_name(wanted):
        return {"ok": False, "code": "bad_args", "error": f"Profile names must be letters, digits or ._- and at most 40 characters: {wanted}",
                "next": "web open --profile work"}
    browser_profiles.choose_profile(root, wanted)
    return None


def cmd_web(args) -> int:
    """Drive a web page. One action at a time — the agent looks at the screen and decides the next one."""
    set_area("web", project_root(args))
    # Attach the harness (guide) matching this URL to the response — actions without a URL use the current page URL (projectops#1023)
    set_target(url=getattr(args, "url", None), root=project_root(args), area="web")
    # A --timeout given in milliseconds would hold the shared browser for 50 minutes — reject before attaching (#931)
    too_large = timeout_failure(args)
    if too_large:
        return out(too_large)
    # A password in --text is stored in plain text in the session log (#604) — take it via --text-env
    secret_value, err = _resolve_secret_text(args)
    if err:
        return out(err)

    action = ACTIONS[args.action]
    if action.needs == "nothing":
        return action.run(args)

    root = project_root(args)
    # web open --profile / --need: decide this repo's profile first (#956) — the state file location follows the profile
    if args.action == "open" and (choice_error := apply_profile_choice(args, root)):
        return out(choice_error)
    if args.action == "open":
        # This session keeps the profile it opened, whatever other sessions in the repo pick later (#1154)
        browser_profiles.pin_session_profile(root)
    state_f = browser_profiles.web_state_path(root)
    # Time limit for the whole command — if attach or the action hangs, report browser_hung and exit (#921)
    watchdog = Watchdog(args.action, deadline_seconds(args, action.needs), state_f).start()
    try:
        return _dispatch(args, action, root, state_f, secret_value)
    finally:
        watchdog.cancel()


def _dispatch(args, action, root, state_f, secret_value: str | None) -> int:
    """Prepare only what the action needs (read state, attach browser) and call it."""
    if action.needs == "launch":
        return action.run(args, root, state_f)

    state = read_state(state_f) if state_f.is_file() else {}
    # web close --stale is unrelated to this project's browser — it runs even with no browser open
    if getattr(args, "stale", False):
        return action.run(args, state, state_f)
    # Viewport and rules can be recorded without a browser — they apply on the next open
    if action.needs == "state_offline":
        return action.run(args, state, state_f)

    if not state.get("cdp"):
        # Keep the main keys even on failure — a json.load(...)["url"] pipe died with KeyError (#931)
        return out({"ok": False, "code": "browser_not_open", "action": args.action, "url": None,
                    "error": "No browser is open",
                    "next": f"web open --root {root} --url <url>"})
    if action.needs == "state_online":
        return action.run(args, state, state_f)

    set_watched_browser(state.get("pid"))
    conn, err = web_connect(state)
    if err:
        # State writes below go to the fresh file and only if it still points to this browser —
        # another session may have relaunched it meanwhile (#1154)
        if err.get("code") == "browser_gone":
            # Clear only the dead browser's info. Viewport and rules were set by a person, so keep them
            update_state_for_browser(state_f, state.get("pid"), _forget_browser)
        elif err.get("code") == "browser_hung":
            # Mark it so the next web open kills and relaunches instead of reattaching
            update_state_for_browser(state_f, state.get("pid"), _mark_hung)
        return out(err)
    pw, _browser, page = conn
    # Warn if the tab changed though this session did not move — another session is using the same tab (#878)
    tab_warning = drift_warning(page, state)
    reloaded = reload_notice(page, state)
    # Last-used time — tells a long-abandoned browser apart from one in use (#825)
    state["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
    update_state_for_browser(state_f, state.get("pid"), lambda fresh: fresh.update(last_used=state["last_used"]))

    # Requests this action caused — did the save really reach the server (#930)
    capture = RequestCapture().attach(page) if getattr(args, "capture_requests", False) else None
    try:
        try:
            payload = action.run(page, args, state)
        except Exception as e:
            payload = _action_failure(args, e, page, secret_value)
        if capture is not None and isinstance(payload, dict):
            payload["requests"] = capture.finish()
        if isinstance(payload, dict):
            _attach_opened_tabs(payload, page, state)
    finally:
        mark_tab(page, state)
        # Only disconnect. Calling browser.close() would leave nothing for the next call to attach to.
        pw.stop()
    _save_tab_mark(state_f, state)
    if isinstance(payload, dict):
        attach_match_warning(payload)
    if tab_warning and isinstance(payload, dict):
        payload["tab_warning"] = tab_warning
    if reloaded and isinstance(payload, dict):
        attach_reload_notice(payload, reloaded)
    _attach_dialog_event(payload, state, state_f)
    # For login input, include the interstitial-screen policy (#905)
    if args.action == "type" and secret_value:
        with_login_policy(payload, getattr(args, "cred", None))
    elif args.action == "login":
        with_login_policy(payload, getattr(args, "login_cred", None))
    return out(payload)


def _action_failure(args, error: Exception, page, secret_value: str | None) -> dict:
    """Exception during an action > web_action_failed. Masks secrets and adds the shared hint for selector syntax errors (#931)"""
    # Exception text may include the input value — mask it if secret before emitting
    message = str(error)
    if secret_value:
        message = message.replace(secret_value, "***")
    payload = {"ok": False, "code": "web_action_failed", "action": args.action,
               "error": message[:400], "url": page.url if page else None,
               "next": "web shot  # look at the current screen first"}
    if is_selector_syntax_error(message):
        payload.update({"selector_syntax_error": True, "hint": SELECTOR_SYNTAX_HINT,
                        "next": "web find --text <text>  # pick by number (ref) instead of writing a selector"})
    return payload


def _attach_opened_tabs(payload: dict, page, state: dict) -> None:
    """Include new windows (popups) this tab opened in the result — so 'URL and title unchanged' is not read as nothing happened (#987)"""
    try:
        new_tabs = opened_tabs(page, state)
    except Exception:
        return  # even if the tab list can't be read, return the action result as is
    if not new_tabs:
        return
    first = new_tabs[0]
    payload["new_tabs"] = new_tabs
    payload["summary"] = f"{payload.get('summary') or ''} — this tab opened {len(new_tabs)} new window(s): {first['url']}".lstrip(" —")
    payload["next"] = (f"web tab use --target {first['target_id']} --name popup  # then prefix commands with LAUNCH_TAB=popup "
                       "to work in the new window")


def _save_tab_mark(state_f, state: dict) -> None:
    """Merge only the tab records into the current file — so values other sessions wrote mid-action (new tabs etc.) are not overwritten."""
    fresh = read_state(state_f) if state_f.is_file() else {}
    if not fresh.get("cdp"):
        return
    fresh["tab_marks"] = {**(fresh.get("tab_marks") or {}), **(state.get("tab_marks") or {})}
    fresh[REPORTED_POPUPS_KEY] = {**(fresh.get(REPORTED_POPUPS_KEY) or {}), **(state.get(REPORTED_POPUPS_KEY) or {})}
    write_state(state_f, fresh)


def _attach_dialog_event(payload: dict, state: dict, state_f) -> None:
    """Include dialogs that appeared during this call in the result, and record in the state file if a set handler was used."""
    event = state.pop(DIALOG_EVENT_KEY, None)
    if not event:
        return
    payload["dialog"] = event
    if event.get("armed"):
        # Only the used-up plan changes; rewriting the whole copy read before the action could undo others' writes
        update_state_for_browser(state_f, state.get("pid"), lambda fresh: fresh.pop("dialog", None))


def _forget_browser(state: dict) -> None:
    for key in ("cdp", "pid"):
        state.pop(key, None)


def _mark_hung(state: dict) -> None:
    state[HUNG_MARK_KEY] = time.strftime("%Y-%m-%d %H:%M:%S")


COMMANDS = [Command(name="web", help="Drive the browser", run=cmd_web, configure=configure)]
