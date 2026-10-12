"""`web open` — 브라우저를 독립 프로세스로 띄우고 CDP 로 붙는다."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import browser_pick
import stealth

from pro_launch.commands.web.session import close_blank_tabs, read_url_title, settle, web_connect
from pro_launch.registry import Action
from pro_launch.runtime.browser import read_state, require_playwright, write_state
from pro_launch.runtime.context import state_home
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import detach_options, pid_alive


def _profile_in_use(profile: Path) -> bool:
    """이 프로필로 떠 있는 브라우저 프로세스가 있나 — 잠금 파일을 지워도 되는지 가른다."""
    try:
        ps = subprocess.run(["ps", "-ax", "-o", "command="], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return True   # 확인 못 하면 쓰는 중으로 본다 — 남의 브라우저 잠금을 지우지 않는다
    return f"--user-data-dir={profile}" in ps


def _web_open(args, root: Path, state_f: Path) -> int:
    sync_playwright, err = require_playwright()
    if err:
        return out(err)
    prev = read_state(state_f)
    # 이미 떠 있으면 새로 띄우지 않고 붙는다 (#825). 예전엔 프로필 잠금 때문에 실패로 끝나
    # agent 가 "브라우저를 못 띄운다"로 읽었는데, 정작 떠 있던 브라우저는 멀쩡히 쓸 수 있었다.
    if prev.get("cdp") and prev.get("pid") and pid_alive(int(prev["pid"])):
        conn, cerr = web_connect(prev)
        if not cerr:
            _pw, _br, _pg = conn
            prev["readonly"] = bool(args.readonly)
            prev["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
            write_state(state_f, prev)
            try:
                if args.url:
                    _pg.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                    settle(_pg, prev, args.timeout)
                url, title = read_url_title(_pg)
            except Exception as e:
                _pw.stop()
                return out({"ok": False, "code": "goto_failed", "error": str(e)[:300],
                            "hint": "주소가 맞는지, 서버가 떠 있는지 확인하세요"})
            _pw.stop()
            warn = None
            if bool(args.headed) != bool(prev.get("headed")):
                warn = "headed 여부는 새로 띄울 때만 바뀐다 — 바꾸려면 web close 후 다시 open"
            return out({"action": "open", "reused": True, "pid": prev["pid"], "url": url, "title": title,
                        "browser": prev.get("browser"), "browser_source": prev.get("browser_source"),
                        "readonly": prev["readonly"], "opened_at": prev.get("opened_at"), "warning": warn,
                        "summary": f"떠 있던 브라우저에 붙었습니다 ({prev.get('opened_at')}부터)",
                        "next": "web text  # 화면 글자를 먼저 읽는다"})
    # 죽은 브라우저가 남긴 잠금은 치운다 — 아무도 이 프로필을 안 쓰는 것을 확인한 뒤에만
    profile_dir = state_home(root) / ".browser-profile"
    if not _profile_in_use(profile_dir):
        for n in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            try:
                (profile_dir / n).unlink()
            except (FileNotFoundError, IsADirectoryError, PermissionError):
                pass
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    # ⚠️ Playwright의 launch()로 띄우면 **드라이버가 죽을 때 브라우저도 함께 죽는다.**
    # 호출이 여러 번으로 쪼개지므로 두 번째 명령이 붙을 곳이 없어진다(실측).
    # 그래서 브라우저를 Playwright 밖에서 독립 프로세스로 띄우고 CDP로 붙는다.
    with sync_playwright() as pw:
        bundled = pw.chromium.executable_path
    pick = browser_pick.resolve(bundled)
    # 환경변수가 틀렸으면 다른 브라우저로 넘어가지 않고 멈춘다 — 지정한 사람이 원한 것은 그것이다
    if pick.get("error"):
        return out({"ok": False, "code": "browser_env_invalid", "error": pick["error"],
                    "next": f"{browser_pick.ENV_VAR} 를 고치거나 지우세요"})
    exe = pick["exe"]
    # 번들도 설치된 브라우저도 없는 경우 — 예외로 죽지 않고 고칠 길을 준다
    if not exe:
        return out({"ok": False, "code": "browser_missing",
                    "error": "Chromium 이 설치돼 있지 않습니다",
                    "path": bundled,
                    "next": ("web setup  # 브라우저(약 100MB)를 받습니다. 내부망이면 Chrome 또는 Edge 를 "
                             f"설치하거나 {browser_pick.ENV_VAR}=<chrome.exe 경로> 로 지정하세요")})
    profile = state_home(root) / ".browser-profile"
    profile.mkdir(parents=True, exist_ok=True)
    cmd = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
           f"--window-size={args.width},{args.height}",
           "--no-first-run", "--no-default-browser-check"]
    # Google·Apple 로그인은 자동화 브라우저를 막는다. 실행 인자는 연결을 끊은 뒤 뜨는 팝업에도 걸린다
    use_stealth = not args.no_stealth
    if use_stealth:
        cmd += stealth.launch_args(exe)
    if not args.headed:
        cmd.append("--headless=new")
    # ⚠️ 목적지를 여기서 넘기면 **훅을 심기 전에 첫 로드가 끝난다** (#625).
    cmd.append("about:blank")
    detach = detach_options()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            **detach)   # 우리가 끝나도 살아 있어야 한다
    cdp = f"http://127.0.0.1:{port}"
    for _ in range(60):
        with socket.socket() as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.25)
    else:
        exit_code = proc.poll()
        proc.terminate()
        # 원인을 가려 준다 — 남은 프로세스·프로필 잠금이면 브라우저를 다시 받아도 소용없다 (#712)
        prev = read_state(state_f)
        stale = prev.get("pid")
        stale_alive = bool(stale) and pid_alive(int(stale))
        locked = any((profile / n).exists() for n in ("SingletonLock", "SingletonSocket"))
        causes = []
        if stale_alive:
            causes.append(f"이전 브라우저(pid {stale})가 아직 살아 있다 → web close 로 정리")
        if locked:
            causes.append("프로필 잠금(SingletonLock)이 남아 있다 → 떠 있는 브라우저가 없으면 잠금 파일을 지운다")
        if exit_code is not None:
            causes.append(f"브라우저가 바로 종료됐다 (종료코드 {exit_code})")
        return out({"ok": False, "code": "browser_start_failed",
                    "error": "브라우저가 뜨지 않았습니다",
                    "causes": causes or None, "stale_pid": stale if stale_alive else None,
                    "profile_locked": locked, "profile": str(profile),
                    "hint": ("; ".join(causes) if causes else
                             "남은 브라우저 프로세스·프로필 잠금을 먼저 확인하고, 그래도 안 되면 web setup 으로 브라우저를 다시 받아 보세요")})

    # 뷰포트·바꿔치기 규칙은 브라우저를 다시 열어도 이어간다 — 설정한 사람이 끈 적이 없다
    prev = read_state(state_f)
    state = {"cdp": cdp, "pid": proc.pid, "headed": bool(args.headed),
             "stealth": use_stealth, "profile": str(profile), "opened_at": time.strftime("%Y-%m-%d %H:%M:%S"),
             "browser": pick["label"], "browser_source": pick["source"],
             "last_used": time.strftime("%Y-%m-%d %H:%M:%S"), "readonly": bool(args.readonly),
             "viewport": prev.get("viewport"), "routes": prev.get("routes") or []}
    write_state(state_f, state)

    hooked = False
    conn, cerr = web_connect(state)
    if not cerr:
        _pw, _br, _pg = conn
        hooked = True
        # 빈 탭 정리 — 이전 open 이 남긴 about:blank 가 누적되는 것을 막는다
        try:
            close_blank_tabs(_pg.context, _pg)
        except Exception:
            pass
        if args.url:
            try:
                _pg.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                settle(_pg, state, args.timeout)
            except Exception as e:
                _br.close(); _pw.stop()
                return out({"ok": False, "code": "goto_failed", "error": str(e),
                            "hint": "주소가 맞는지, 서버가 떠 있는지 확인하세요"})
        _br.close()
        _pw.stop()
    return out({"action": "open", "url": args.url, "cdp": cdp, "pid": proc.pid,
                "state_file": str(state_f), "console_hook": hooked,
                "routes": len(state["routes"]), "viewport": state["viewport"],
                "stealth": use_stealth, "readonly": bool(args.readonly), "reused": False,
                "browser": pick["label"], "browser_source": pick["source"], "browser_reason": pick["reason"],
                "summary": f"브라우저를 열었습니다 ({args.url or '빈 탭'})"
                           + (" — 읽기 전용" if args.readonly else ""),
                "next": "web text  # 화면 글자를 먼저 읽는다 (모양을 봐야 할 때만 web shot)"})


def configure(p) -> None:
    p.add_argument("--headed", action="store_true",
                   help="open: 눈에 보이게 연다 — 소셜 로그인이 막히면 이것이 먼저다(#604 실측)")
    p.add_argument("--no-stealth", action="store_true",
                   help="open: 자동화 표식 가리기를 끈다 (사이트가 깨질 때 비교용)")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800)
    p.add_argument("--readonly", action="store_true",
                   help="open: 읽기 전용 세션 — 삭제·출시·제출 같은 버튼은 --confirm-mutating 없이 누르지 않는다")


ACTION = Action(name="open", needs="launch", run=_web_open, configure=configure)
