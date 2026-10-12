"""`web` — 브라우저를 직접 몬다 (#586).

agent 가 스크린샷을 보고 다음 수를 정하므로 조작이 여러 번의 CLI 호출로 쪼개진다.
상주 데몬을 만들지 않고 **CDP 재연결**로 푼다.

    open  → --remote-debugging-port 로 독립 프로세스를 띄우고 포트를 상태 파일에 적는다
    이후  → connect_over_cdp 로 그 브라우저에 붙었다 떨어진다 (세션·쿠키 유지)

⚠️ 붙어 있는 동안에만 사는 것이 있다 — 콘솔 훅 · 뷰포트 · 응답 바꿔치기. 연결이 끊기면 같이 사라진다
(#625 실측). 그래서 상태 파일에 적어 두고 **붙을 때마다 다시 건다** (`session.web_connect`).

동작 하나는 `actions/` 의 모듈 하나다. 이 파일은 공통 옵션을 달고, 동작이 필요로 하는 만큼만
준비(상태 읽기 · 브라우저 붙기)해서 부른다. 동작을 추가해도 이 파일은 고치지 않는다.
"""
from __future__ import annotations

import os
import time

from pro_launch.commands.web import actions as _actions
from pro_launch.commands.web.session import web_connect
from pro_launch.registry import Command, discover_actions
from pro_launch.runtime.browser import read_state, state_path, write_state
from pro_launch.runtime.context import project_root
from pro_launch.runtime.creds import cred_field
from pro_launch.runtime.output import out, set_area
from pro_launch.runtime.shots import add_shot_args

ACTIONS = discover_actions(_actions)


def configure(p) -> None:
    # 여러 동작이 함께 쓰는 옵션. 한 동작만 쓰는 옵션은 그 동작의 configure 에 둔다
    p.add_argument("action", choices=sorted(ACTIONS))
    p.add_argument("--root", default=".")
    p.add_argument("--url", default=None, help="주소 (open·goto·assert)")
    p.add_argument("--selector", default=None,
                   help="대상 (click·type·assert·shot). text=로그인 · #id · button:has-text('x')")
    p.add_argument("--text", default=None, help="입력할 값 또는 확인할 문구")
    p.add_argument("--cred", default=None, help="저장된 로그인 정보로 입력한다 (cred list). 값은 명령줄에 남지 않는다")
    p.add_argument("--cred-field", dest="cred_field", default=None, help="--cred 에서 넣을 필드 (기본 password, 예: account)")
    p.add_argument("--text-env", dest="text_env", default=None,
                   help="입력값을 환경변수에서 읽는다 — 비밀번호는 반드시 이쪽")
    p.add_argument("--timeout", type=int, default=10, help="대기 제한(초)")
    p.add_argument("--clear", action="store_true", help="viewport·route: 지정을 푼다")
    add_shot_args(p)
    for action in ACTIONS.values():
        if action.configure:
            action.configure(p)


def cmd_web(args) -> int:
    """웹 화면을 조작한다. 한 번에 한 동작 — agent가 화면을 보고 다음을 정한다."""
    set_area("web", project_root(args))
    # 비밀번호를 --text 에 적으면 세션 기록에 평문으로 남는다(#604) — --text-env 로 받는다
    secret_value = None
    if getattr(args, "text_env", None):
        if args.text_env not in os.environ:
            return out({"ok": False, "code": "env_not_set",
                        "error": f"환경변수 {args.text_env} 가 비어 있습니다",
                        "hint": f'{args.text_env}="..." 를 같은 명령 앞에 붙여 실행하세요'})
        secret_value = os.environ[args.text_env]
        args.text = secret_value
    elif getattr(args, "cred", None):
        # 저장된 로그인 정보를 입력한다 — 명령줄·기록에 값이 남지 않는다
        value, err = cred_field(args.cred, getattr(args, "cred_field", None))
        if err:
            return out(err)
        secret_value = value
        args.text = value

    action = ACTIONS[args.action]
    if action.needs == "nothing":
        return action.run(args)

    root = project_root(args)
    state_f = state_path(root)
    if action.needs == "launch":
        return action.run(args, root, state_f)

    state = read_state(state_f) if state_f.is_file() else {}
    # 뷰포트·규칙은 브라우저 없이도 적어 둘 수 있다 — 다음 open 에서 걸린다
    if action.needs == "state_offline":
        return action.run(args, state, state_f)

    if not state.get("cdp"):
        return out({"ok": False, "code": "browser_not_open", "error": "열린 브라우저가 없습니다",
                    "next": f"web open --root {root} --url <주소>"})
    if action.needs == "state_online":
        return action.run(args, state, state_f)

    conn, err = web_connect(state)
    if err:
        if err.get("code") == "browser_gone":
            # 죽은 브라우저 정보만 지운다. 뷰포트·규칙은 사람이 정한 것이라 남긴다
            for k in ("cdp", "pid"):
                state.pop(k, None)
            write_state(state_f, state)
        return out(err)
    pw, _browser, page = conn
    # 마지막 사용 시각 — 오래 방치된 브라우저와 지금 쓰는 브라우저를 가른다 (#825)
    state["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_state(state_f, state)

    try:
        return out(action.run(page, args, state))
    except Exception as e:
        # 예외 문구에 입력값이 섞여 나올 수 있다 — 비밀값이면 가리고 내보낸다
        msg = str(e)
        if secret_value:
            msg = msg.replace(secret_value, "***")
        return out({"ok": False, "code": "web_action_failed", "action": args.action,
                    "error": msg[:400], "url": page.url if page else None,
                    "next": "web shot  # 지금 화면이 무엇인지 먼저 봅니다"})
    finally:
        # 연결만 끊는다. browser.close()를 부르면 다음 호출이 붙을 곳이 없어진다.
        pw.stop()


COMMANDS = [Command(name="web", help="브라우저를 조작한다", run=cmd_web, configure=configure)]
