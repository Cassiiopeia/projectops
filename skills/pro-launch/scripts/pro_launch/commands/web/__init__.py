"""`web` — 브라우저를 직접 몬다 (#586).

agent 가 스크린샷을 보고 다음 수를 정하므로 조작이 여러 번의 CLI 호출로 쪼개진다.
상주 데몬을 만들지 않고 **CDP 재연결**로 푼다.

    open  → --remote-debugging-port 로 독립 프로세스를 띄우고 포트를 상태 파일에 적는다
    이후  → connect_over_cdp 로 그 브라우저에 붙었다 떨어진다 (세션·쿠키 유지)

⚠️ 붙어 있는 동안에만 사는 것이 있다 — 콘솔 훅 · 뷰포트 · 응답 바꿔치기 · 대화상자 처리. 연결이 끊기면 같이 사라진다
(#625 실측). 그래서 상태 파일에 적어 두고 **붙을 때마다 다시 건다** (`session.web_connect`).

동작 하나는 `actions/` 의 모듈 하나다. 이 파일은 동작마다 하위 파서(공통 옵션 중 그 동작이 쓰는 것 + 자기 옵션)를 달고,
동작이 필요로 하는 만큼만 준비(상태 읽기 · 브라우저 붙기)해서 부른다. 동작을 추가해도 이 파일은 고치지 않는다.
"""
from __future__ import annotations

import argparse
import os
import time

from pro_launch.commands.web import actions as _actions
from pro_launch.commands.web.options import ALWAYS_OPTIONS, SHARED_OPTIONS
from pro_launch.commands.web.session import DIALOG_EVENT_KEY, web_connect
from pro_launch.registry import Command, action_usage_lines, add_action_parsers, discover_actions
from pro_launch.runtime.browser import read_state, state_path, write_state
from pro_launch.runtime.context import project_root
from pro_launch.runtime.creds import cred_field
from pro_launch.runtime.output import out, set_area

ACTIONS = discover_actions(_actions)


def configure(p) -> None:
    # 동작별 하위 파서 — `web <동작> --help` 는 그 동작이 쓰는 옵션만 보여 준다 (#895)
    add_action_parsers(p, ACTIONS, SHARED_OPTIONS, always=ALWAYS_OPTIONS)
    p.formatter_class = argparse.RawDescriptionHelpFormatter
    p.description = "브라우저를 조작한다. 한 번에 한 동작 — 자세한 옵션은 web <동작> --help"
    p.epilog = "동작별 옵션:\n" + "\n".join(action_usage_lines(p))


def _resolve_secret_text(args) -> tuple[str | None, dict | None]:
    """--text-env · --cred 에서 입력값을 꺼내 args.text 에 넣는다. (비밀값, 실패 결과)"""
    if getattr(args, "text_env", None):
        if args.text_env not in os.environ:
            return None, {"ok": False, "code": "env_not_set",
                          "error": f"환경변수 {args.text_env} 가 비어 있습니다",
                          "hint": f'{args.text_env}="..." 를 같은 명령 앞에 붙여 실행하세요'}
        args.text = os.environ[args.text_env]
        return args.text, None
    if getattr(args, "cred", None):
        # 저장된 로그인 정보를 입력한다 — 명령줄·기록에 값이 남지 않는다
        value, err = cred_field(args.cred, getattr(args, "cred_field", None))
        if err:
            return None, err
        args.text = value
        return value, None
    return None, None


def cmd_web(args) -> int:
    """웹 화면을 조작한다. 한 번에 한 동작 — agent가 화면을 보고 다음을 정한다."""
    set_area("web", project_root(args))
    # 비밀번호를 --text 에 적으면 세션 기록에 평문으로 남는다(#604) — --text-env 로 받는다
    secret_value, err = _resolve_secret_text(args)
    if err:
        return out(err)

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
        payload = action.run(page, args, state)
    except Exception as e:
        # 예외 문구에 입력값이 섞여 나올 수 있다 — 비밀값이면 가리고 내보낸다
        msg = str(e)
        if secret_value:
            msg = msg.replace(secret_value, "***")
        payload = {"ok": False, "code": "web_action_failed", "action": args.action,
                   "error": msg[:400], "url": page.url if page else None,
                   "next": "web shot  # 지금 화면이 무엇인지 먼저 봅니다"}
    finally:
        # 연결만 끊는다. browser.close()를 부르면 다음 호출이 붙을 곳이 없어진다.
        pw.stop()
    _attach_dialog_event(payload, state, state_f)
    return out(payload)


def _attach_dialog_event(payload: dict, state: dict, state_f) -> None:
    """이번 호출 중에 뜬 대화상자를 결과에 싣고, 걸어 둔 처리를 썼으면 상태 파일에 남긴다."""
    event = state.pop(DIALOG_EVENT_KEY, None)
    if not event:
        return
    payload["dialog"] = event
    write_state(state_f, state)


COMMANDS = [Command(name="web", help="브라우저를 조작한다", run=cmd_web, configure=configure)]
