"""Attach to the open browser and re-apply settings that only live while attached (CDP reconnect)."""
from __future__ import annotations

import time

import stealth

from pro_launch.commands.web import tabs
from pro_launch.commands.web.recovery import HUNG_PROBE_SECONDS, cdp_responds
from pro_launch.commands.web.watchdog import connect_phase
from pro_launch.runtime.browser import idle_hours, require_playwright
from pro_launch.runtime.procs import pid_alive

# Time limit (seconds) for connect_over_cdp itself — shorter than the watchdog's attach limit (30s) so it fails cleanly first
CONNECT_TIMEOUT_SECONDS = 20


# Console errors happen **while the page loads**. Adding the listener after load is too late (#625).
_CONSOLE_HOOK = r"""
(() => {
  if (window.__projectops_console) return;
  const buf = [];
  window.__projectops_console = buf;
  const push = (type, text) => {
    try { buf.push({ type, text: String(text).slice(0, 2000), at: Date.now() }); } catch (e) {}
    if (buf.length > 500) buf.splice(0, buf.length - 500);   // keep it from growing forever
  };
  for (const level of ["log", "info", "warn", "error"]) {
    const orig = console[level];
    console[level] = function (...args) {
      push(level, args.map((a) => {
        try { return typeof a === "string" ? a : JSON.stringify(a); }
        catch (e) { return String(a); }
      }).join(" "));
      return orig.apply(console, args);
    };
  }
  // Errors that bypass console.error — these are often the real incidents
  window.addEventListener("error", (e) => push("error", e.message || String(e.error || e)));
  window.addEventListener("unhandledrejection",
    (e) => push("error", "unhandled rejection: " + String(e.reason)));
})();
"""


def install_console_hook(page) -> bool:
    try:
        page.add_init_script(_CONSOLE_HOOK)
        return True
    except Exception:
        return False


def apply_routes(page, rules: list[dict]) -> int:
    """Install response-override rules. They live only while this connection is attached."""
    n = 0
    for rule in rules:
        # Playwright calls handler(route, request). Binding rule as a default argument lets
        # the second argument (request) overwrite it — hit in practice. Bind with a closure.
        page_route = _route_handler(rule)
        try:
            page.route(rule["match"], page_route)
            n += 1
        except Exception:
            continue
    return n


def _route_handler(rule: dict):
    def handler(route, *_):
        if rule.get("delay_ms"):
            time.sleep(rule["delay_ms"] / 1000)
        if rule.get("status") is None:
            route.continue_()
            return
        route.fulfill(status=int(rule["status"]),
                      headers={"content-type": rule.get("content_type") or "application/json",
                               "access-control-allow-origin": "*"},
                      body=rule.get("body") or "")
    return handler


def install_stealth(ctx, page) -> bool:
    """Install the automation-marker hiding script. Installed on the context so popups opened while attached (login windows) are covered too."""
    ok = True
    for script in stealth.init_scripts():
        try:
            ctx.add_init_script(script)
        except Exception:
            try:
                page.add_init_script(script)
            except Exception:
                ok = False
    return ok


def close_blank_tabs(ctx, keep) -> int:
    """Close about:blank tabs other than the working tab (keep).
    Each web open starts on about:blank and the persistent profile restores old tabs, so blank tabs pile up."""
    closed = 0
    for pg in list(ctx.pages):
        try:
            if pg != keep and pg.url == "about:blank":
                pg.close()
                closed += 1
        except Exception:
            pass  # tab closed in the meantime — skip
    return closed


def web_connect(state: dict, allow_missing_tab: bool = False):
    """Attach to the open browser and re-apply settings that only live while attached (hooks, stealth, viewport, rules, dialogs).

    Tab: the tab named by LAUNCH_TAB if set, otherwise the last tab not claimed by another session (#878).
    allow_missing_tab: attach to the default tab even if the named tab is gone (when web tab shows the list).
    """
    sync_playwright, err = require_playwright()
    if err:
        return None, err
    # Detect a hung browser first — a Playwright connection waits a long time on an unresponsive CDP (#887)
    is_process_alive = bool(state.get("pid")) and pid_alive(int(state["pid"]))
    if is_process_alive and not cdp_responds(state["cdp"]):
        return None, _hung_failure(state, f"Browser did not respond within {HUNG_PROBE_SECONDS:g}s (the process exists but is hung)")
    # The watchdog bounds the attach phase separately — even when CDP answers, connect or tab listing has hung (#921)
    with connect_phase():
        pw = sync_playwright().start()
        try:
            browser = pw.chromium.connect_over_cdp(state["cdp"], timeout=CONNECT_TIMEOUT_SECONDS * 1000)
        except Exception as e:
            pw.stop()
            # Alive but timed out means hung — reporting browser_gone would make the dispatcher drop the pid and orphan it
            if is_process_alive and "timeout" in str(e).lower():
                return None, _hung_failure(state, f"Could not attach to the browser within {CONNECT_TIMEOUT_SECONDS}s (connection hung)")
            # Alive but attach failed: not gone. Reporting browser_gone made the caller drop a live pid (#1154)
            if is_process_alive:
                return None, {"ok": False, "code": "browser_attach_failed", "pid": state.get("pid"), "url": None,
                              "error": f"The browser is running but attaching failed: {str(e)[:300]}",
                              "hint": "Often transient (the page was redirecting or closing tabs). The browser and its state are kept",
                              "next": "Retry the same command; if it keeps failing, web open"}
            # Why it ended is unknown — the profile's exit_type stays Crashed even after a normal window close (#1094, observed)
            return None, {"ok": False, "code": "browser_gone", "last_used": state.get("last_used"), "idle_hours": idle_hours(state),
                          "hint": "A closed window, a crash and another session's web close look the same from here",
                          "error": f"The browser is gone (last used {state.get('last_used')}). Attach error: {e}",
                          "next": "web open  # open it again"}
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page, tab_error = _session_page(ctx, state, allow_missing_tab)
    if tab_error:
        pw.stop()
        return None, tab_error
    # Old state files (no key) count as enabled — disabled only when --no-stealth is given explicitly
    if state.get("stealth", True):
        install_stealth(ctx, page)
    install_console_hook(page)
    vp = state.get("viewport")
    if vp:
        try:
            page.set_viewport_size({"width": int(vp[0]), "height": int(vp[1])})
        except Exception:
            pass  # even if sizing fails, open the session at the default size
    apply_routes(page, state.get("routes") or [])
    arm_dialog(page, state)
    return (pw, browser, page), None


def _hung_failure(state: dict, error: str) -> dict:
    """Hung-browser result — includes which process and profile (needed to kill it manually)"""
    return {"ok": False, "code": "browser_hung", "pid": state.get("pid"), "profile": state.get("profile"),
            "url": None, "error": error,
            "next": "web open  # kills the hung browser and starts it again (self-recovery)"}


def _session_page(ctx, state: dict, allow_missing_tab: bool):
    """Tab this session drives > (page, failure result)."""
    name = tabs.session_tab_name()
    if name:
        page = tabs.named_tab_page(ctx, state, name)
        if page is not None:
            return page, None
        if not allow_missing_tab:
            return None, {"ok": False, "code": "tab_gone",
                          "error": f"Tab {tabs.TAB_ENV_VAR}={name} does not exist (closed, or the browser restarted)",
                          "next": f"web tab new --name {name}  # create a new tab with the same name (or web tab list)"}
    last_used = tabs.last_used_tab_page(ctx, state)
    if last_used is not None:
        return last_used, None
    if state.get("tabs"):
        return tabs.default_tab_page(ctx, state), None
    # Use the last tab. The profile is persistent so Chromium revives old tabs,
    # and taking pages[0] would drive that old tab instead of the one just opened (observed).
    return work_page(ctx), None


# State key handing this call's dialog records to the dispatcher — cleared once included in the result
DIALOG_EVENT_KEY = "_dialog_event"


def arm_dialog(page, state: dict) -> bool:
    """Install dialog (alert, confirm, prompt) handling. Re-installed on every attach — it disappears when the connection drops (#625).

    A handler set with `web dialog` (state["dialog"]) is used for the next dialog only, then cleared.
    With no handler set, dismiss — same as Playwright's default — and only record that it appeared.
    """
    try:
        page.on("dialog", dialog_handler(state))
        return True
    except Exception:
        return False


def dialog_handler(state: dict):
    def handler(dialog) -> None:
        plan = state.pop("dialog", None) or {}
        should_accept = plan.get("action") == "accept"
        event = {"type": getattr(dialog, "type", None), "message": (getattr(dialog, "message", "") or "")[:300],
                 "handled": "accept" if should_accept else "dismiss", "armed": bool(plan)}
        try:
            if should_accept:
                prompt_text = plan.get("text")
                dialog.accept(prompt_text) if prompt_text is not None else dialog.accept()
            else:
                dialog.dismiss()
        except Exception as e:   # dialog already closed — just record it
            event["error"] = str(e)[:200]
        state[DIALOG_EVENT_KEY] = event
    return handler


# Guide tabs Chrome opens on its own. Not working tabs
_BROWSER_INTERNAL = ("chrome://", "chrome-untrusted://", "devtools://", "edge://")


def work_page(ctx):
    """Pick the tab to work in.

    The persistent profile revives old tabs, and installed Chrome opens guide tabs (chrome://privacy-sandbox-dialog etc.)
    on startup. Using the last tab blindly may grab that guide tab, which Chrome closes as soon as we navigate,
    failing with 'Target page, context or browser has been closed' (#860, observed; order varied between runs).
    Use the last non-chrome:// tab; open a new one if there is none.
    """
    live = [p for p in ctx.pages if not p.is_closed()]
    usable = [p for p in live if not p.url.startswith(_BROWSER_INTERNAL)]
    return usable[-1] if usable else ctx.new_page()


def safe_title(page) -> str:
    """Read the title. Reading mid-redirect throws 'Execution context was destroyed',
    so wait for the load to finish and read again (#860)."""
    return read_url_title(page)[1]


def read_url_title(page, timeout: int = 10) -> tuple[str, str]:
    """Read URL and title. Calling title() during a server or script redirect
    throws 'Execution context was destroyed' — wait for the load to finish and read again."""
    for _ in range(3):
        try:
            page.wait_for_load_state("load", timeout=timeout * 1000)
        except Exception:
            pass  # even if loading is slow, try reading below and loop again on failure
        try:
            return page.url, page.title()
        except Exception:
            time.sleep(0.5)
    return page.url, ""


def settle(page, state: dict, timeout: int) -> None:
    """If override rules exist, wait until all requests finish.

    Rules vanish when this connection drops. If we detach before loading finishes, late API requests
    get real responses — that is why a staged empty list ends up filled.
    """
    if not state.get("routes"):
        return
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout, 15) * 1000)
    except Exception:
        pass  # pages where networkidle never comes (long polling etc.) — waiting up to the limit is enough


def done_payload(action: str, page) -> dict:
    """Common result for actions that did not change the screen (goto, type) — reports the current URL and title.

    Read URL and title together. Reading separately can mix values from different moments across a redirect.
    """
    url, title = read_url_title(page)
    return {"action": action, "url": url, "title": title,
            "summary": f"{action} done — {url}",
            "next": "web text  # read the text of the resulting screen"}
