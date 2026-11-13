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
from pro_launch.runtime.browser import find_stale_browsers, read_state, require_playwright, write_state
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import detach_options, kill_browser, manual_kill_command
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
    """이번 open 이 몰 탭 > (page, 탭 이름, 자동 분리 여부).
    이름 없이 왔는데 고른 탭을 다른 세션이 쓰는 중이면 덮지 않고 이 세션 몫의 새 탭을 뒤에 연다 (#1094)."""
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
    """방치 브라우저 자동 정리 > 끈 목록 (#1027). 지금 붙을 브라우저는 제외, 정리 실패로 open 을 막지 않음"""
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
    """떠 있는 브라우저에 붙는다. 붙기에서 멈췄으면 None — 호출부가 끄고 새로 띄운다 (#921)"""
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
    write_state(state_f, prev)
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


# 브라우저를 띄울 때만 먹는 설정. 이미 떠 있는 브라우저에는 적용되지 않는다.
# 여기에 한 줄 더하면 실행 인자 · 상태 기록 · 재시작 경고가 함께 따라온다
LAUNCH_ONLY_SETTINGS = (
    # 서버 응답 뒤 window.open 이 null 로 막힌다 (Playwright launch 는 기본으로 넣는 플래그, #987)
    {"flag": "--disable-popup-blocking", "state_key": "popup_blocking_off",
     "warning": "This browser was started before popup blocking was turned off — a window opened after a server "
                "response can be blocked. Run web close, then web open again"},
    # Playwright 는 붙어 있는 동안 prefers-color-scheme 을 light 로 덮어쓰고(CDP 연결은 바꿀 옵션이 없다) 끊으면 되돌린다.
    # 다크 모드 PC 에서는 명령마다 테마가 두 번 뒤집혀, 테마 변화에 새로고침하는 사이트(YouTube Studio)가 매번 다시 로드됐다 (#1094 실측).
    # 브라우저의 실제 값을 light 로 고정하면 뒤집힐 일이 없다
    {"flag": "--blink-settings=preferredColorScheme=1", "state_key": "light_color_scheme",
     "warning": "This browser was started before the color scheme was pinned — on a dark-mode PC, sites that reload on a theme "
                "change (YouTube Studio) reload at every command. Run web close, then web open again"},
)


def _launch_command(exe: str, port: int, profile: Path, args, use_stealth: bool) -> list[str]:
    cmd = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
           f"--window-size={args.width},{args.height}", "--no-first-run", "--no-default-browser-check",
           *(setting["flag"] for setting in LAUNCH_ONLY_SETTINGS)]
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
    stale_closed = _close_stale_browsers(prev.get("pid"))
    # 레포 프로필 또는 고른 공용 프로필 (#956)
    profile = browser_profiles.profile_home(root) / browser_profiles.PROFILE_FOLDER_NAME
    decision, recovered = recover_recorded_browser(prev, profile)
    # 이미 떠 있으면 새로 띄우지 않고 붙는다 (#825). 새로 띄우면 프로필 잠금으로 실패한다
    if decision == "reuse":
        reused = _reuse(args, prev, state_f, recovered, stale_closed)
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
             "stealth": use_stealth, "profile": str(profile), "opened_at": now, **{setting["state_key"]: True for setting in LAUNCH_ONLY_SETTINGS},
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
