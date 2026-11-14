"""`web open` — launch the browser as an independent process and attach over CDP.

Recorded browser verdict (#887): alive and responding > reattach · hung > stop and relaunch · dead > clear leftover locks and relaunch.
What was cleaned up is returned as `recovered`. State lost a browser still running on the profile > adopt it (#1154). Tabs (#878): `--new-tab` · `--tab-name` · `LAUNCH_TAB` give a session its own tab.
"""
from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

import browser_pick
import stealth

from pro_launch.commands.web import tabs
from pro_launch.commands.web.recovery import (
    BROWSER_STDERR_FILE, cdp_responds, has_profile_lock, recover_recorded_browser, stderr_tail)
from pro_launch.commands.web.session import close_blank_tabs, read_url_title, settle, web_connect
from pro_launch.commands.web.watchdog import HUNG_MARK_KEY, set_watched_browser
from pro_launch.registry import Action
from pro_launch.runtime import browser_profiles
from pro_launch.runtime.browser import (
    find_stale_browsers, read_state, require_playwright, running_browser_on_profile, write_state)
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import detach_options, kill_browser, manual_kill_command, pid_alive
from pro_launch.runtime.session_identity import session_identity

# Attempts and interval for waiting on a new browser's CDP port (about 15 seconds)
_PORT_WAIT_TRIES = 60
_PORT_WAIT_INTERVAL_SECONDS = 0.25


def _cert_hint(msg: str) -> str | None:
    """For self-signed or private certificates, explain the fix. Most internal servers hit this."""
    if "ERR_CERT" in msg or "ERR_SSL" in msg:
        return ("Blocked by a private/self-signed certificate — run web close, then reopen with "
                "`web open --ignore-cert-errors --url ...` (test servers only; applies to a fresh launch)")
    return None


def _goto_failed(error: Exception) -> dict:
    return {"ok": False, "code": "goto_failed", "error": str(error)[:300],
            "hint": _cert_hint(str(error)) or "Check that the URL is right and the server is up"}


def _pick_tab(ctx, page, state: dict, args):
    """Tab this open will drive > (page, tab name, whether auto-split).
    If no name was given and the chosen tab is in use by another session, do not take it over; open a new tab for this session at the end (#1094)."""
    name = args.tab_name or tabs.session_tab_name()
    if name:
        existing = tabs.named_tab_page(ctx, state, name)
        if existing is not None:
            return existing, name, False
    if args.new_tab or name:
        name = name or f"tab-{time.strftime('%H%M%S')}"
        page = tabs.new_tab_page(ctx, is_front=args.front)
        tabs.register_tab(state, name, page)
        return page, name, False
    if tabs.is_other_session_tab(page, state):
        return tabs.new_tab_page(ctx, is_front=args.front), None, True
    return page, name, False


def _close_stale_browsers(pid_to_keep) -> list[dict]:
    """Auto-clean abandoned browsers > list of stopped ones (#1027). Skips the browser about to be attached; cleanup failure never blocks open"""
    closed = []
    try:
        for entry in find_stale_browsers()["stale"]:
            if str(entry["pid"]) != str(pid_to_keep) and not kill_browser(int(entry["pid"]), grace=2.0):
                closed.append({"pid": entry["pid"], "profile": entry["profile"], "reasons": entry["reasons"]})
    except Exception:
        return closed
    return closed


def _stale_closed_note(stale_closed: list[dict]) -> str:
    return f" — closed {len(stale_closed)} abandoned browsers" if stale_closed else ""


def _reuse(args, prev: dict, state_f: Path, recovered: list[str], stale_closed: list[dict]) -> int | None:
    """Attach to a running browser. None if attaching hung — the caller stops it and relaunches (#921)"""
    conn, connect_error = web_connect(prev, allow_missing_tab=True)
    if connect_error:
        if connect_error.get("code") == "browser_hung":
            return None
        return out(connect_error)
    pw, _browser, page = conn
    try:
        page, tab_name, is_isolated = _pick_tab(page.context, page, prev, args)
        if args.url:
            page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
            settle(page, prev, args.timeout)
        url, title = read_url_title(page)
        tab_summary = tabs.tabs_summary(page.context, page, prev, tab_name)
        prev.setdefault("tab_marks", {})[tabs.mark_key(tab_name)] = tabs.tab_mark(page)
        other_sessions = tabs.active_other_sessions(prev)
    except Exception as e:
        pw.stop()
        return out(_goto_failed(e))
    pw.stop()
    prev["readonly"] = bool(args.readonly)
    prev["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _merge_reuse_state(state_f, prev)
    warnings = []
    if bool(args.headed) != bool(prev.get("headed")):
        warnings.append("headed only changes on a fresh launch — to change it, run web close, then open again")
    warnings += [setting["warning"] for setting in LAUNCH_ONLY_SETTINGS if not prev.get(setting["state_key"])]
    warn = " / ".join(warnings) or None
    return out({"action": "open", "reused": True, "pid": prev["pid"], "url": url, "title": title,
                "browser": prev.get("browser"), "browser_source": prev.get("browser_source"),
                "readonly": prev["readonly"], "opened_at": prev.get("opened_at"), "warning": warn,
                "tabs": tab_summary, "recovered": recovered, "stale_closed": stale_closed,
                "other_sessions": other_sessions, "isolated_from_other_session": is_isolated,
                "summary": f"Attached to the running browser (since {prev.get('opened_at')}, {tab_summary['count']} tabs)"
                           + (" — another session was using that tab, so this session got its own background tab" if is_isolated else "")
                           + _stale_closed_note(stale_closed),
                "next": "web text  # read the screen text first"})


def _merge_reuse_state(state_f: Path, prev: dict) -> None:
    """Write what this open changed onto the fresh file — other sessions' tab records written meanwhile stay (#1154)."""
    fresh = read_state(state_f) if state_f.is_file() else {}
    if str(fresh.get("pid")) != str(prev.get("pid")):
        # Adopted browser or first write: the file has nothing newer for this browser
        write_state(state_f, prev)
        return
    fresh.update(readonly=prev["readonly"], last_used=prev["last_used"])
    for key in ("tabs", "tab_marks"):
        fresh[key] = {**(fresh.get(key) or {}), **(prev.get(key) or {})}
    write_state(state_f, fresh)


def _adopt_running_browser(prev: dict, profile: Path, root: Path) -> dict | None:
    """State lost its browser but one still runs on this profile > state pointing to it. Else None.

    Launching again would die on the profile lock (browser_start_failed, #1154).
    """
    recorded_pid = prev.get("pid")
    if recorded_pid and pid_alive(int(recorded_pid)):
        return None
    running = running_browser_on_profile(profile)
    if running is None or not cdp_responds(running["cdp"]):
        return None
    adopted = {key: value for key, value in prev.items() if key != HUNG_MARK_KEY}
    adopted.update(running, profile=str(profile), profile_name=browser_profiles.chosen_profile(root))
    adopted.setdefault("opened_at", time.strftime("%Y-%m-%d %H:%M:%S"))
    return adopted


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, proc) -> bool:
    for _ in range(_PORT_WAIT_TRIES):
        # Do not wait 15 seconds for a browser that died immediately
        if proc.poll() is not None:
            return False
        with socket.socket() as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(_PORT_WAIT_INTERVAL_SECONDS)
    return False


def _start_failed(proc, profile: Path, stderr_log: Path, recovered: list[str]) -> dict:
    """Pin down the cause — with a leftover process or profile lock, re-downloading the browser does not help (#712)."""
    exit_code = proc.poll()
    proc.terminate()
    locked = has_profile_lock(profile)
    causes = []
    if locked:
        causes.append("The profile lock is still held and another process uses this profile → end that browser, then reopen")
    if exit_code is not None:
        causes.append(f"The browser exited immediately (exit code {exit_code})")
    return {"ok": False, "code": "browser_start_failed", "error": "Browser did not start",
            "causes": causes or None, "profile_locked": locked, "profile": str(profile),
            "recovered": recovered, "stderr_tail": stderr_tail(stderr_log),
            "hint": ("; ".join(causes) if causes else
                     "Read stderr_tail first; if that does not explain it, re-download the browser with web setup")}


# Settings that only apply at browser launch. A browser already running does not pick them up.
# Add one line here and launch args, state record and restart warning all follow
LAUNCH_ONLY_SETTINGS = (
    # window.open after a server response is blocked as null (a flag Playwright launch adds by default, #987)
    {"flag": "--disable-popup-blocking", "state_key": "popup_blocking_off",
     "warning": "This browser was started before popup blocking was turned off — a window opened after a server "
                "response can be blocked. Run web close, then web open again"},
    # While attached, Playwright overrides prefers-color-scheme to light (CDP connect has no option to change it) and reverts on disconnect.
    # On a dark-mode PC the theme flipped twice per command, so sites that reload on theme change (YouTube Studio) reloaded every time (#1094 observed).
    # Pinning the browser's real value to light means nothing flips
    {"flag": "--blink-settings=preferredColorScheme=1", "state_key": "light_color_scheme",
     "warning": "This browser was started before the color scheme was pinned — on a dark-mode PC, sites that reload on a theme "
                "change (YouTube Studio) reload at every command. Run web close, then web open again"},
)


def _launch_command(exe: str, port: int, profile: Path, args, use_stealth: bool) -> list[str]:
    cmd = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
           f"--window-size={args.width},{args.height}", "--no-first-run", "--no-default-browser-check",
           *(setting["flag"] for setting in LAUNCH_ONLY_SETTINGS)]
    # Google and Apple logins block automated browsers. Launch args also apply to popups opened after disconnect
    if use_stealth:
        cmd += stealth.launch_args(exe)
    if args.ignore_cert_errors:
        cmd.append("--ignore-certificate-errors")
    if not args.headed:
        cmd.append("--headless=new")
    # ⚠️ Passing the destination here finishes the first load **before the hooks are installed** (#625).
    cmd.append("about:blank")
    return cmd


def _web_open(args, root: Path, state_f: Path) -> int:
    sync_playwright, err = require_playwright()
    if err:
        return out(err)
    prev = read_state(state_f)
    # Repo profile or the chosen shared profile (#956)
    profile = browser_profiles.profile_home(root) / browser_profiles.PROFILE_FOLDER_NAME
    adopted = _adopt_running_browser(prev, profile, root)
    if adopted is not None:
        prev = adopted
        write_state(state_f, prev)
    stale_closed = _close_stale_browsers(prev.get("pid"))
    set_watched_browser(prev.get("pid"))
    decision, recovered = recover_recorded_browser(prev, profile)
    if adopted is not None:
        recovered = ["adopted_running_browser", *recovered]
    # If already running, attach instead of launching (#825). Launching again fails on the profile lock
    if decision == "reuse":
        reused = _reuse(args, prev, state_f, recovered, stale_closed)
        if reused is not None:
            return reused
        # CDP answers but attaching hung — stop it and relaunch with the same profile (login cookies stay in the profile)
        decision, recovered = recover_recorded_browser({**prev, HUNG_MARK_KEY: "connect"}, profile)
    if decision == "blocked":
        pid = prev.get("pid")
        return out({"ok": False, "code": "browser_still_alive", "pid": pid,
                    "error": f"Could not stop the unresponsive browser (pid {pid})",
                    "next": f"{manual_kill_command(pid)}  # end it yourself, then reopen"})

    # ⚠️ Launching via Playwright's launch() makes **the browser die together with the driver.**
    # Calls are split across several runs, so launch the browser outside Playwright as an independent process and attach over CDP.
    with sync_playwright() as pw:
        bundled = pw.chromium.executable_path
    pick = browser_pick.resolve(bundled)
    # If the env var is wrong, stop instead of falling back to another browser — that is what whoever set it wanted
    if pick.get("error"):
        return out({"ok": False, "code": "browser_env_invalid", "error": pick["error"],
                    "next": f"Fix or unset {browser_pick.ENV_VAR}"})
    exe = pick["exe"]
    if not exe:
        return out({"ok": False, "code": "browser_missing", "error": "Chromium is not installed",
                    "path": bundled,
                    "next": ("web setup  # downloads the browser (about 100MB). On an internal network, install Chrome or Edge "
                             f"or set {browser_pick.ENV_VAR}=<path to chrome.exe>")})
    profile.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    use_stealth = not args.no_stealth
    stderr_log = browser_profiles.profile_home(root) / BROWSER_STDERR_FILE
    with open(stderr_log, "w", encoding="utf-8") as stderr_file:
        # Must outlive us. Stderr is included as the failure cause
        proc = subprocess.Popen(_launch_command(exe, port, profile, args, use_stealth),
                                stdout=subprocess.DEVNULL, stderr=stderr_file, **detach_options())
    if not _wait_for_port(port, proc):
        return out(_start_failed(proc, profile, stderr_log, recovered))

    # Viewport and override rules carry over — whoever set them never turned them off. Tab records are invalid in a new browser
    cdp = f"http://127.0.0.1:{port}"
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    state = {"cdp": cdp, "pid": proc.pid, "headed": bool(args.headed),
             "stealth": use_stealth, "profile": str(profile), "opened_at": now, **{setting["state_key"]: True for setting in LAUNCH_ONLY_SETTINGS},
             "browser": pick["label"], "browser_source": pick["source"],
             "last_used": now, "readonly": bool(args.readonly),
             # At session end, close only browsers this session launched (#956)
             "opened_by_session": session_identity(), "profile_name": browser_profiles.chosen_profile(root),
             "viewport": prev.get("viewport"), "routes": prev.get("routes") or []}
    write_state(state_f, state)
    set_watched_browser(proc.pid)

    hooked, tab_summary = False, None
    conn, cerr = web_connect(state, allow_missing_tab=True)
    if not cerr:
        _pw, _br, page = conn
        hooked = True
        try:
            # Clean up blank tabs — stops about:blank tabs left by earlier opens from piling up
            close_blank_tabs(page.context, page)
            name = args.tab_name or tabs.session_tab_name()
            if name:
                tabs.register_tab(state, name, page)
            if args.url:
                page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                settle(page, state, args.timeout)
            tab_summary = tabs.tabs_summary(page.context, page, state, name)
            state.setdefault("tab_marks", {})[tabs.mark_key(name)] = tabs.tab_mark(page)
        except Exception as e:
            _pw.stop()
            return out(_goto_failed(e))
        _pw.stop()
        write_state(state_f, state)
    return out({"action": "open", "url": args.url, "cdp": cdp, "pid": proc.pid,
                "state_file": str(state_f), "console_hook": hooked,
                "routes": len(state["routes"]), "viewport": state["viewport"],
                "stealth": use_stealth, "readonly": bool(args.readonly), "reused": False,
                "recovered": recovered, "stale_closed": stale_closed, "tabs": tab_summary,
                "browser": pick["label"], "browser_source": pick["source"], "browser_reason": pick["reason"],
                "profile": browser_profiles.chosen_profile(root) or browser_profiles.REPO_PROFILE_NAME,
                "summary": f"Opened the browser ({args.url or 'blank tab'})"
                           + (" — read-only" if args.readonly else "")
                           + (f" — cleaned up: {', '.join(recovered)}" if recovered else "")
                           + _stale_closed_note(stale_closed),
                "next": "web text  # read the screen text first (web shot only when you need to see the layout)"})


def configure(p) -> None:
    p.add_argument("--headed", action="store_true",
                   help="open: open a visible window — try this first when social login is blocked (#604)")
    p.add_argument("--no-stealth", action="store_true",
                   help="open: turn off hiding of automation markers (to compare when a site breaks)")
    p.add_argument("--ignore-cert-errors", action="store_true",
                   help="open: ignore self-signed/private certificate errors — for internal test servers; applies to a fresh launch")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800)
    p.add_argument("--readonly", action="store_true",
                   help="open: read-only session — buttons like delete, release or submit are not pressed without --confirm-mutating")
    p.add_argument("--new-tab", dest="new_tab", action="store_true",
                   help="open: open in a new tab of the running browser — to keep tabs apart from other sessions")
    p.add_argument("--front", action="store_true",
                   help="open: bring a newly created tab to the front (default: new tabs open in the background)")
    p.add_argument("--tab-name", dest="tab_name", default=None,
                   help="open: name this tab. Then LAUNCH_TAB=<name> drives only this tab")
    p.add_argument("--profile", default=None,
                   help="open: shared profile name on this computer — reuses the same login across repos (repo = the repo profile). Remembered per repo")
    p.add_argument("--need", action="append", default=None,
                   help="open: pick the profile marked with this state (kind:name, e.g. login:google) (web profile mark)")


ACTION = Action(name="open", needs="launch", run=_web_open, configure=configure, options=("url", "timeout"), positional="url",
                help="Launch the browser as a separate process (reattaches if running; cleans up by itself if hung or locked)",
                example="web open --url http://localhost:3000 --headed")
