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
from pro_launch.runtime.browser import read_state, require_playwright, write_state
from pro_launch.runtime.context import state_home
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import detach_options, manual_kill_command

# 새로 띄운 브라우저의 CDP 포트가 열리길 기다리는 횟수 · 간격 (약 15초)
_PORT_WAIT_TRIES = 60
_PORT_WAIT_INTERVAL_SECONDS = 0.25


def _cert_hint(msg: str) -> str | None:
    """자체서명·사설 인증서면 고칠 길을 준다. 사내 서버는 대부분 이 경우다."""
    if "ERR_CERT" in msg or "ERR_SSL" in msg:
        return ("사설/자체서명 인증서로 막혔다 — web close 후 `web open --ignore-cert-errors --url ...` "
                "로 다시 연다 (테스트 서버 전용, 새로 띄울 때만 적용)")
    return None


def _goto_failed(error: Exception) -> dict:
    return {"ok": False, "code": "goto_failed", "error": str(error)[:300],
            "hint": _cert_hint(str(error)) or "주소가 맞는지, 서버가 떠 있는지 확인하세요"}


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
    warn = None
    if bool(args.headed) != bool(prev.get("headed")):
        warn = "headed 여부는 새로 띄울 때만 바뀐다 — 바꾸려면 web close 후 다시 open"
    return out({"action": "open", "reused": True, "pid": prev["pid"], "url": url, "title": title,
                "browser": prev.get("browser"), "browser_source": prev.get("browser_source"),
                "readonly": prev["readonly"], "opened_at": prev.get("opened_at"), "warning": warn,
                "tabs": tab_summary, "recovered": recovered,
                "summary": f"떠 있던 브라우저에 붙었습니다 ({prev.get('opened_at')}부터, 탭 {tab_summary['count']}개)",
                "next": "web text  # 화면 글자를 먼저 읽는다"})


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
        causes.append("프로필 잠금이 남아 있고 이 프로필을 쓰는 다른 프로세스가 있다 → 그 브라우저를 끝낸 뒤 다시 연다")
    if exit_code is not None:
        causes.append(f"브라우저가 바로 종료됐다 (종료코드 {exit_code})")
    return {"ok": False, "code": "browser_start_failed", "error": "브라우저가 뜨지 않았습니다",
            "causes": causes or None, "profile_locked": locked, "profile": str(profile),
            "recovered": recovered, "stderr_tail": stderr_tail(stderr_log),
            "hint": ("; ".join(causes) if causes else
                     "stderr_tail 을 먼저 보고, 그래도 모르겠으면 web setup 으로 브라우저를 다시 받아 보세요")}


def _launch_command(exe: str, port: int, profile: Path, args, use_stealth: bool) -> list[str]:
    cmd = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
           f"--window-size={args.width},{args.height}", "--no-first-run", "--no-default-browser-check"]
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
    profile = state_home(root) / ".browser-profile"
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
                    "error": f"응답 없는 브라우저(pid {pid})를 끄지 못했습니다",
                    "next": f"{manual_kill_command(pid)}  # 직접 종료한 뒤 다시 여세요"})

    # ⚠️ Playwright의 launch()로 띄우면 **드라이버가 죽을 때 브라우저도 함께 죽는다.**
    # 호출이 여러 번으로 쪼개지므로 브라우저를 Playwright 밖에서 독립 프로세스로 띄우고 CDP로 붙는다.
    with sync_playwright() as pw:
        bundled = pw.chromium.executable_path
    pick = browser_pick.resolve(bundled)
    # 환경변수가 틀렸으면 다른 브라우저로 넘어가지 않고 멈춘다 — 지정한 사람이 원한 것은 그것이다
    if pick.get("error"):
        return out({"ok": False, "code": "browser_env_invalid", "error": pick["error"],
                    "next": f"{browser_pick.ENV_VAR} 를 고치거나 지우세요"})
    exe = pick["exe"]
    if not exe:
        return out({"ok": False, "code": "browser_missing", "error": "Chromium 이 설치돼 있지 않습니다",
                    "path": bundled,
                    "next": ("web setup  # 브라우저(약 100MB)를 받습니다. 내부망이면 Chrome 또는 Edge 를 "
                             f"설치하거나 {browser_pick.ENV_VAR}=<chrome.exe 경로> 로 지정하세요")})
    profile.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    use_stealth = not args.no_stealth
    stderr_log = state_home(root) / BROWSER_STDERR_FILE
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
             "stealth": use_stealth, "profile": str(profile), "opened_at": now,
             "browser": pick["label"], "browser_source": pick["source"],
             "last_used": now, "readonly": bool(args.readonly),
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
                "summary": f"브라우저를 열었습니다 ({args.url or '빈 탭'})"
                           + (" — 읽기 전용" if args.readonly else "")
                           + (f" — 치운 것: {', '.join(recovered)}" if recovered else ""),
                "next": "web text  # 화면 글자를 먼저 읽는다 (모양을 봐야 할 때만 web shot)"})


def configure(p) -> None:
    p.add_argument("--headed", action="store_true",
                   help="open: 눈에 보이게 연다 — 소셜 로그인이 막히면 이것이 먼저다(#604 실측)")
    p.add_argument("--no-stealth", action="store_true",
                   help="open: 자동화 표식 가리기를 끈다 (사이트가 깨질 때 비교용)")
    p.add_argument("--ignore-cert-errors", action="store_true",
                   help="open: 자체서명·사설 인증서 오류를 무시한다 — 사내 테스트 서버용, 새로 띄울 때만 적용")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800)
    p.add_argument("--readonly", action="store_true",
                   help="open: 읽기 전용 세션 — 삭제·출시·제출 같은 버튼은 --confirm-mutating 없이 누르지 않는다")
    p.add_argument("--new-tab", dest="new_tab", action="store_true",
                   help="open: 떠 있는 브라우저에 새 탭을 만들어 연다 — 다른 세션과 탭을 나눠 쓸 때")
    p.add_argument("--tab-name", dest="tab_name", default=None,
                   help="open: 이 탭에 이름을 붙인다. 이후 LAUNCH_TAB=<이름> 으로 이 탭만 몬다")


ACTION = Action(name="open", needs="launch", run=_web_open, configure=configure, options=("url", "timeout"),
                help="브라우저를 독립 프로세스로 띄운다 (떠 있으면 다시 붙고, 멈췄거나 잠금이 남았으면 스스로 정리)",
                example="web open --url http://localhost:3000 --headed")
