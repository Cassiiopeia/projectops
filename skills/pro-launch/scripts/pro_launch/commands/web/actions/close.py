"""`web close` — 브라우저를 닫는다 · --stale 버려진 것 정리 · --session-end 이 세션이 띄운 것 정리 (#956)."""
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
    # ⚠️ 살아 있으면 상태 파일을 남긴다. 지우면 떠 있는 브라우저에 다시 붙을 길이 사라진다(실측).
    if alive:
        return out({"ok": False, "code": "browser_still_alive", "pid": pid,
                    "error": f"The browser (pid {pid}) is still alive",
                    "next": f"{manual_kill_command(pid)}  # end it yourself, then reopen"})
    state_f.unlink(missing_ok=True)
    return out({"action": "close", "summary": "Closed the browser"})


def _close_by_connection(state: dict, state_f: Path) -> int:
    """pid 를 모르는 옛 상태 파일 — 연결해서 닫는 수밖에 없다."""
    conn, err = web_connect(state)
    if err:
        if err.get("code") == "browser_gone":
            # 죽은 브라우저 정보만 지운다. 뷰포트·규칙은 사람이 정한 것이라 남긴다
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
    """pro-launch 가 띄우고 버려진 브라우저만 끈다 (프로필 사라짐 · 상태 파일이 안 가리킴 · 오래 쉼). 쓰는 중인 것은 보고만"""
    found = find_stale_browsers(maximum_idle_hours=args.idle_hours)
    if not found["readable"]:
        return out({"ok": False, "code": "process_list_unreadable", "action": "close", "stale": [], "kept": [],
                    "error": "Could not read the process list, so abandoned browsers cannot be identified"})
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
    """세션 종료: 이 세션이 띄웠고 다른 세션 탭이 없는 브라우저만 닫는다 (쿠키는 프로필에 남아 로그인은 유지)."""
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
        # 연결부터 맺지 않는다 — 응답 없는 브라우저에서는 연결·close 가 모두 멈춘다 (#712)
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
