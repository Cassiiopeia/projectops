"""`web close` — close the browser · --stale cleans up abandoned ones · --session-end cleans up what this session launched (#956)."""
from __future__ import annotations

from pathlib import Path

from pro_launch.commands.web.session import web_connect
from pro_launch.registry import Action
from pro_launch.runtime import browser_profiles
from pro_launch.runtime.browser import find_stale_browsers, read_state, write_state
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import kill_browser, manual_kill_command, pid_alive
from pro_launch.runtime.session_identity import session_identity


def _web_close(state: dict, state_f: Path) -> int:
    pid = state.get("pid")
    alive = False
    if pid:
        try:
            alive = kill_browser(int(pid))
        except ValueError:
            pass
    # ⚠️ If it is alive, keep the state file. Deleting it loses the way back to the running browser (observed).
    if alive:
        return out({"ok": False, "code": "browser_still_alive", "pid": pid,
                    "error": f"The browser (pid {pid}) is still alive",
                    "next": f"{manual_kill_command(pid)}  # end it yourself, then reopen"})
    state_f.unlink(missing_ok=True)
    return out({"action": "close", "summary": "Closed the browser"})


def _close_by_connection(state: dict, state_f: Path) -> int:
    """Old state file without a pid — the only way is to connect and close."""
    conn, err = web_connect(state)
    if err:
        if err.get("code") == "browser_gone":
            # Remove only the dead browser's info. Viewport and rules were set by a person, so keep them
            for k in ("cdp", "pid"):
                state.pop(k, None)
            write_state(state_f, state)
        return out(err)
    pw, browser, _page = conn
    try:
        browser.close()
        state_f.unlink(missing_ok=True)
        return out({"action": "close", "summary": "Closed the browser"})
    except Exception as e:
        return out({"ok": False, "code": "web_action_failed", "action": "close",
                    "error": str(e)[:400], "next": "web shot  # first see what is on screen now"})
    finally:
        pw.stop()


def _close_stale(args) -> int:
    """Stop only abandoned browsers pro-launch launched (profile gone · not pointed to by a state file · idle long). In-use ones are only reported"""
    found = find_stale_browsers(maximum_idle_hours=args.idle_hours)
    if not found["readable"]:
        return out({"ok": False, "code": "process_list_unreadable", "action": "close", "stale": [], "kept": [],
                    "error": "Could not read the process list, so abandoned browsers cannot be identified",
                    "next": "Nothing was closed. web close without --stale still closes this session browser"})
    closed, still_alive = [], []
    for entry in found["stale"]:
        if not args.dry_run and kill_browser(int(entry["pid"]), grace=2.0):
            still_alive.append(entry)
        elif not args.dry_run:
            closed.append(entry)
    summary = (f"{len(found['stale'])} abandoned browsers (not stopped, --dry-run)" if args.dry_run else
               f"Stopped {len(closed)} abandoned browsers; kept {len(found['kept'])} that are in use")
    return out({"ok": not still_alive, "code": "ok" if not still_alive else "browser_still_alive",
                "action": "close", "stale": found["stale"], "closed": closed, "kept": found["kept"],
                "still_alive": still_alive, "dry_run": args.dry_run, "summary": summary,
                "next": "kept may be in use by another session — close them with that session's web close"})


def _close_session_browsers() -> int:
    """Session end: close only browsers this session launched that hold no other session's tabs (cookies stay in the profile, so logins persist)."""
    session, closed, kept = session_identity(), [], []
    for state_file in browser_profiles.all_web_state_files():
        state = read_state(state_file)
        pid = state.get("pid")
        if state.get("opened_by_session") != session or not pid or not pid_alive(int(pid)):
            continue
        others = browser_profiles.other_session_tabs(state, session)
        if others:
            kept.append({"state_file": str(state_file), "pid": pid, "other_session_tabs": others})
            continue
        if kill_browser(int(pid), grace=2.0):
            kept.append({"state_file": str(state_file), "pid": pid, "reason": "still_alive"})
            continue
        state_file.unlink(missing_ok=True)
        closed.append({"state_file": str(state_file), "pid": pid, "profile": state.get("profile_name") or "repo"})
    return out({"action": "close", "session_end": True, "closed": closed, "kept": kept,
                "summary": f"Closed {len(closed)} browsers this session started" + (f" · kept {len(kept)}" if kept else ""),
                "next": None})


def execute(args, state: dict, state_f: Path) -> int:
    if args.stale:
        return _close_stale(args)
    if getattr(args, "session_end", False):
        return _close_session_browsers()
    if state.get("pid"):
        # Do not connect first — on an unresponsive browser both connect and close hang (#712)
        return _web_close(state, state_f)
    return _close_by_connection(state, state_f)


def configure(p) -> None:
    p.add_argument("--stale", action="store_true",
                   help="Clean up abandoned pro-launch browsers instead of this project's (profile gone · no state file points to it · idle a long time)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", help="--stale: list only, do not stop")
    p.add_argument("--session-end", dest="session_end", action="store_true",
                   help="Close only browsers this session started that have no other session's tabs (used by the session-end hook)")
    p.add_argument("--idle-hours", dest="idle_hours", type=float, default=12,
                   help="--stale: treat a browser with no parent unused for this many hours as abandoned (default 12)")


ACTION = Action(name="close", needs="state_online", run=execute, configure=configure, options=(),
                help="Close the browser (--stale: clean up abandoned browsers)", example="web close --stale --dry-run")
