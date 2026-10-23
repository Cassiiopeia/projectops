"""`web open` — 브라우저를 독립 프로세스로 띄우고 CDP 로 붙는다.

기록된 브라우저 판정 (#887): 살아 있고 응답 > 다시 붙는다 · 멈춤 > 끄고 새로 · 죽음 > 남은 잠금 정리 후 새로.
치운 것은 `recovered` 로 돌려준다. 탭 (#878): `--new-tab` · `--tab-name` · `LAUNCH_TAB` 으로 세션 전용 탭을 쓴다.
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
    BROWSER_STDERR_FILE, has_profile_lock, recover_recorded_browser, stderr_tail)
from pro_launch.commands.web.session import close_blank_tabs, read_url_title, settle, web_connect
from pro_launch.commands.web.watchdog import HUNG_MARK_KEY
from pro_launch.registry import Action
from pro_launch.runtime import browser_profiles
from pro_launch.runtime.browser import read_state, require_playwright, write_state
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import detach_options, manual_kill_command
from pro_launch.runtime.session_identity import session_identity

# 새로 띄운 브라우저의 CDP 포트가 열리길 기다리는 횟수 · 간격 (약 15초)
_PORT_WAIT_TRIES = 60
_PORT_WAIT_INTERVAL_SECONDS = 0.25


def _cert_hint(msg: str) -> str | None:
    """자체서명·사설 인증서면 고칠 길을 준다. 사내 서버는 대부분 이 경우다."""
    if "ERR_CERT" in msg or "ERR_SSL" in msg:
        return ("Blocked by a private/self-signed certificate — run web close, then reopen with "
                "`web open --ignore-cert-errors --url ...` (test servers only; applies to a fresh launch)")
    return None


def _goto_failed(error: Exception) -> dict:
    return {"ok": False, "code": "goto_failed", "error": str(error)[:300],
            "hint": _cert_hint(str(error)) or "Check that the URL is right and the server is up"}


def _pick_tab(ctx, page, state: dict, args):
    """이번 open 이 몰 탭 > (page, 탭 이름). --new-tab 이거나 이름 붙은 탭이 없으면 새 탭을 만들어 그 이름으로 기록한다."""
    name = args.tab_name or tabs.session_tab_name()
    if name:
        existing = tabs.named_tab_page(ctx, state, name)
        if existing is not None:
            return existing, name
    if args.new_tab or name:
        name = name or f"tab-{time.strftime('%H%M%S')}"
        page = ctx.new_page()
        tabs.register_tab(state, name, page)
    return page, name


def _reuse(args, prev: dict, state_f: Path, recovered: list[str]) -> int | None:
    """떠 있는 브라우저에 붙는다. 붙기에서 멈췄으면 None — 호출부가 끄고 새로 띄운다 (#921)"""
    conn, connect_error = web_connect(prev, allow_missing_tab=True)
    if connect_error:
        if connect_error.get("code") == "browser_hung":
            return None
        return out(connect_error)
    pw, _browser, page = conn
    try:
        page, tab_name = _pick_tab(page.context, page, prev, args)
        if args.url:
            page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
            settle(page, prev, args.timeout)
        url, title = read_url_title(page)
        tab_summary = tabs.tabs_summary(page.context, page, prev, tab_name)
        prev.setdefault("tab_marks", {})[tabs.mark_key(tab_name)] = {"target_id": tabs.target_id(page), "url": url}
    except Exception as e:
        pw.stop()
        return out(_goto_failed(e))
    pw.stop()
    prev["readonly"] = bool(args.readonly)
    prev["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_state(state_f, prev)
    warnings = []
    if bool(args.headed) != bool(prev.get("headed")):
        warnings.append("headed only changes on a fresh launch — to change it, run web close, then open again")
    if not prev.get(POPUP_BLOCKING_OFF_STATE_KEY):
        warnings.append("This browser was started before popup blocking was turned off — a window opened after a server "
                        "response can be blocked. Run web close, then web open again")
    warn = " / ".join(warnings) or None
    return out({"action": "open", "reused": True, "pid": prev["pid"], "url": url, "title": title,
                "browser": prev.get("browser"), "browser_source": prev.get("browser_source"),
                "readonly": prev["readonly"], "opened_at": prev.get("opened_at"), "warning": warn,
                "tabs": tab_summary, "recovered": recovered,
                "summary": f"Attached to the running browser (since {prev.get('opened_at')}, {tab_summary['count']} tabs)",
                "next": "web text  # read the screen text first"})


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, proc) -> bool:
    for _ in range(_PORT_WAIT_TRIES):
        # 바로 죽은 브라우저를 15초 기다리지 않는다
        if proc.poll() is not None:
            return False
        with socket.socket() as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(_PORT_WAIT_INTERVAL_SECONDS)
    return False


def _start_failed(proc, profile: Path, stderr_log: Path, recovered: list[str]) -> dict:
    """원인을 가려 준다 — 남은 프로세스·프로필 잠금이면 브라우저를 다시 받아도 소용없다 (#712)."""
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


# 팝업 차단 끄기 플래그 · 그 플래그로 띄웠는지 상태 파일 키
POPUP_BLOCKING_OFF_FLAG = "--disable-popup-blocking"
POPUP_BLOCKING_OFF_STATE_KEY = "popup_blocking_off"


def _launch_command(exe: str, port: int, profile: Path, args, use_stealth: bool) -> list[str]:
    # --disable-popup-blocking: 서버 응답 뒤 window.open 이 null 로 막힌다 (Playwright launch 는 기본으로 넣는 플래그, #987)
    cmd = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
           f"--window-size={args.width},{args.height}", "--no-first-run", "--no-default-browser-check",
           POPUP_BLOCKING_OFF_FLAG]
    # Google·Apple 로그인은 자동화 브라우저를 막는다. 실행 인자는 연결을 끊은 뒤 뜨는 팝업에도 걸린다
    if use_stealth:
        cmd += stealth.launch_args(exe)
    if args.ignore_cert_errors:
        cmd.append("--ignore-certificate-errors")
    if not args.headed:
        cmd.append("--headless=new")
    # ⚠️ 목적지를 여기서 넘기면 **훅을 심기 전에 첫 로드가 끝난다** (#625).
    cmd.append("about:blank")
    return cmd


def _web_open(args, root: Path, state_f: Path) -> int:
    sync_playwright, err = require_playwright()
    if err:
        return out(err)
    prev = read_state(state_f)
    # 레포 프로필 또는 고른 공용 프로필 (#956)
    profile = browser_profiles.profile_home(root) / browser_profiles.PROFILE_FOLDER_NAME
    decision, recovered = recover_recorded_browser(prev, profile)
    # 이미 떠 있으면 새로 띄우지 않고 붙는다 (#825). 새로 띄우면 프로필 잠금으로 실패한다
    if decision == "reuse":
        reused = _reuse(args, prev, state_f, recovered)
        if reused is not None:
            return reused
        # CDP 는 답하는데 붙기가 멈췄다 — 끄고 같은 프로필로 새로 띄운다 (로그인 쿠키는 프로필에 남는다)
        decision, recovered = recover_recorded_browser({**prev, HUNG_MARK_KEY: "connect"}, profile)
    if decision == "blocked":
        pid = prev.get("pid")
        return out({"ok": False, "code": "browser_still_alive", "pid": pid,
                    "error": f"Could not stop the unresponsive browser (pid {pid})",
                    "next": f"{manual_kill_command(pid)}  # end it yourself, then reopen"})

    # ⚠️ Playwright의 launch()로 띄우면 **드라이버가 죽을 때 브라우저도 함께 죽는다.**
    # 호출이 여러 번으로 쪼개지므로 브라우저를 Playwright 밖에서 독립 프로세스로 띄우고 CDP로 붙는다.
    with sync_playwright() as pw:
        bundled = pw.chromium.executable_path
    pick = browser_pick.resolve(bundled)
    # 환경변수가 틀렸으면 다른 브라우저로 넘어가지 않고 멈춘다 — 지정한 사람이 원한 것은 그것이다
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
        # 우리가 끝나도 살아 있어야 한다. 표준오류는 실패 원인으로 싣는다
        proc = subprocess.Popen(_launch_command(exe, port, profile, args, use_stealth),
                                stdout=subprocess.DEVNULL, stderr=stderr_file, **detach_options())
    if not _wait_for_port(port, proc):
        return out(_start_failed(proc, profile, stderr_log, recovered))

    # 뷰포트·바꿔치기 규칙은 이어간다 — 설정한 사람이 끈 적이 없다. 탭 기록은 새 브라우저에서 무효다
    cdp = f"http://127.0.0.1:{port}"
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    state = {"cdp": cdp, "pid": proc.pid, "headed": bool(args.headed),
             "stealth": use_stealth, "profile": str(profile), "opened_at": now, POPUP_BLOCKING_OFF_STATE_KEY: True,
             "browser": pick["label"], "browser_source": pick["source"],
             "last_used": now, "readonly": bool(args.readonly),
             # 세션 종료 때 이 세션이 띄운 브라우저만 닫는다 (#956)
             "opened_by_session": session_identity(), "profile_name": browser_profiles.chosen_profile(root),
             "viewport": prev.get("viewport"), "routes": prev.get("routes") or []}
    write_state(state_f, state)

    hooked, tab_summary = False, None
    conn, cerr = web_connect(state, allow_missing_tab=True)
    if not cerr:
        _pw, _br, page = conn
        hooked = True
        try:
            # 빈 탭 정리 — 이전 open 이 남긴 about:blank 가 누적되는 것을 막는다
            close_blank_tabs(page.context, page)
            name = args.tab_name or tabs.session_tab_name()
            if name:
                tabs.register_tab(state, name, page)
            if args.url:
                page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                settle(page, state, args.timeout)
            tab_summary = tabs.tabs_summary(page.context, page, state, name)
            state.setdefault("tab_marks", {})[tabs.mark_key(name)] = {"target_id": tabs.target_id(page), "url": page.url}
        except Exception as e:
            _pw.stop()
            return out(_goto_failed(e))
        _pw.stop()
        write_state(state_f, state)
    return out({"action": "open", "url": args.url, "cdp": cdp, "pid": proc.pid,
                "state_file": str(state_f), "console_hook": hooked,
                "routes": len(state["routes"]), "viewport": state["viewport"],
                "stealth": use_stealth, "readonly": bool(args.readonly), "reused": False,
                "recovered": recovered, "tabs": tab_summary,
                "browser": pick["label"], "browser_source": pick["source"], "browser_reason": pick["reason"],
                "profile": browser_profiles.chosen_profile(root) or browser_profiles.REPO_PROFILE_NAME,
                "summary": f"Opened the browser ({args.url or 'blank tab'})"
                           + (" — read-only" if args.readonly else "")
                           + (f" — cleaned up: {', '.join(recovered)}" if recovered else ""),
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
    p.add_argument("--tab-name", dest="tab_name", default=None,
                   help="open: name this tab. Then LAUNCH_TAB=<name> drives only this tab")
    p.add_argument("--profile", default=None,
                   help="open: shared profile name on this computer — reuses the same login across repos (repo = the repo profile). Remembered per repo")
    p.add_argument("--need", action="append", default=None,
                   help="open: pick the profile marked with this state (kind:name, e.g. login:google) (web profile mark)")


ACTION = Action(name="open", needs="launch", run=_web_open, configure=configure, options=("url", "timeout"),
                help="Launch the browser as a separate process (reattaches if running; cleans up by itself if hung or locked)",
                example="web open --url http://localhost:3000 --headed")
