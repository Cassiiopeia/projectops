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
                    "error": f"브라우저(pid {pid})가 아직 살아 있습니다",
                    "next": f"{manual_kill_command(pid)}  # 직접 종료한 뒤 다시 여세요"})
    state_f.unlink(missing_ok=True)
    return out({"action": "close", "summary": "브라우저를 닫았습니다"})


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
        return out({"action": "close", "summary": "브라우저를 닫았습니다"})
    except Exception as e:
        return out({"ok": False, "code": "web_action_failed", "action": "close",
                    "error": str(e)[:400], "next": "web shot  # 지금 화면이 무엇인지 먼저 봅니다"})
    finally:
        pw.stop()


def _close_stale(args) -> int:
    """pro-launch 가 띄우고 버려진 브라우저만 끈다 (프로필 사라짐 · 상태 파일이 안 가리킴 · 오래 쉼). 쓰는 중인 것은 보고만"""
    found = find_stale_browsers(maximum_idle_hours=args.idle_hours)
    if not found["readable"]:
        return out({"ok": False, "code": "process_list_unreadable", "action": "close", "stale": [], "kept": [],
                    "error": "프로세스 목록을 읽지 못해 버려진 브라우저를 가를 수 없습니다"})
    closed, still_alive = [], []
    for entry in found["stale"]:
        if not args.dry_run and kill_browser(int(entry["pid"]), grace=2.0):
            still_alive.append(entry)
        elif not args.dry_run:
            closed.append(entry)
    summary = (f"버려진 브라우저 {len(found['stale'])}개 (끄지 않음 --dry-run)" if args.dry_run else
               f"버려진 브라우저 {len(closed)}개를 끄고 {len(found['kept'])}개는 쓰는 중이라 두었다")
    return out({"ok": not still_alive, "code": "ok" if not still_alive else "browser_still_alive",
                "action": "close", "stale": found["stale"], "closed": closed, "kept": found["kept"],
                "still_alive": still_alive, "dry_run": args.dry_run, "summary": summary,
                "next": "kept 는 다른 세션이 쓰는 중일 수 있다 — 그 세션의 web close 로 끈다"})


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
                "summary": f"이 세션이 띄운 브라우저 {len(closed)}개를 닫았다" + (f" · {len(kept)}개는 남김" if kept else ""),
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
                   help="이 프로젝트가 아니라 버려진 pro-launch 브라우저(프로필 사라짐 · 상태 파일이 안 가리킴 · 오래 쉼)를 정리한다")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", help="--stale: 끄지 않고 목록만")
    p.add_argument("--session-end", dest="session_end", action="store_true",
                   help="이 세션이 띄웠고 다른 세션 탭이 없는 브라우저만 닫는다 (세션 종료 훅이 쓴다)")
    p.add_argument("--idle-hours", dest="idle_hours", type=float, default=12,
                   help="--stale: 부모 없이 이만큼(시간) 안 쓴 브라우저를 버려진 것으로 본다 (기본 12)")


ACTION = Action(name="close", needs="state_online", run=execute, configure=configure, options=(),
                help="브라우저를 닫는다 (--stale: 버려진 브라우저 정리)", example="web close --stale --dry-run")
