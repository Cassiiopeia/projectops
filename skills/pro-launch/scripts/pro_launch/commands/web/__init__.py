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
from pro_launch.commands.web.element import attach_match_warning
from pro_launch.commands.web.options import ALWAYS_OPTIONS, SHARED_OPTIONS, timeout_failure
from pro_launch.commands.web.request_capture import RequestCapture
from pro_launch.commands.web.saved_values import read_saved_values
from pro_launch.commands.web.session import DIALOG_EVENT_KEY, web_connect
from pro_launch.commands.web.tabs import drift_warning, mark_tab
from pro_launch.commands.web.targets import SELECTOR_SYNTAX_HINT, is_selector_syntax_error
from pro_launch.commands.web.watchdog import HUNG_MARK_KEY, Watchdog, deadline_seconds
from pro_launch.registry import Command, action_usage_lines, add_action_parsers, discover_actions
from pro_launch.runtime.browser import read_state, state_path, write_state
from pro_launch.runtime.context import project_root
from pro_launch.runtime.creds import cred_field, with_login_policy
from pro_launch.runtime.output import out, set_area

ACTIONS = discover_actions(_actions)


def configure(p) -> None:
    # 동작별 하위 파서 — `web <동작> --help` 는 그 동작이 쓰는 옵션만 보여 준다 (#896)
    add_action_parsers(p, ACTIONS, SHARED_OPTIONS, always=ALWAYS_OPTIONS)
    p.formatter_class = argparse.RawDescriptionHelpFormatter
    p.description = "브라우저를 조작한다. 한 번에 한 동작 — 자세한 옵션은 web <동작> --help"
    p.epilog = "동작별 옵션:\n" + "\n".join(action_usage_lines(p))


def _resolve_secret_text(args) -> tuple[str | None, dict | None]:
    """--text-env · --cred 에서 입력값을 꺼내 args.text 에 넣는다. (비밀값, 실패 결과)

    --text-env: 환경변수 > 없으면 web value · clipboard --save-env 로 저장한 값 (#930)
    """
    if getattr(args, "text_env", None):
        value = os.environ.get(args.text_env)
        if value is None:
            value = read_saved_values(project_root(args)).get(args.text_env)
        if value is None:
            return None, {"ok": False, "code": "env_not_set",
                          "error": f"환경변수 {args.text_env} 가 비어 있습니다 (저장한 값에도 없음)",
                          "hint": f'{args.text_env}="..." 를 같은 명령 앞에 붙이거나 web value --save-env {args.text_env} 로 저장하세요'}
        args.text = value
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
    # 밀리초로 준 --timeout 이 공유 브라우저를 50분 붙잡는다 — 붙기 전에 거절 (#931)
    too_large = timeout_failure(args)
    if too_large:
        return out(too_large)
    # 비밀번호를 --text 에 적으면 세션 기록에 평문으로 남는다(#604) — --text-env 로 받는다
    secret_value, err = _resolve_secret_text(args)
    if err:
        return out(err)

    action = ACTIONS[args.action]
    if action.needs == "nothing":
        return action.run(args)

    root = project_root(args)
    state_f = state_path(root)
    # 명령 전체 시간 상한 — 붙기 · 조작이 멈추면 browser_hung 을 내고 끝낸다 (#921)
    watchdog = Watchdog(args.action, deadline_seconds(args, action.needs), state_f).start()
    try:
        return _dispatch(args, action, root, state_f, secret_value)
    finally:
        watchdog.cancel()


def _dispatch(args, action, root, state_f, secret_value: str | None) -> int:
    """동작이 필요로 하는 만큼 준비(상태 읽기 · 브라우저 붙기)해서 부른다."""
    if action.needs == "launch":
        return action.run(args, root, state_f)

    state = read_state(state_f) if state_f.is_file() else {}
    # web close --stale 은 이 프로젝트의 브라우저와 무관하다 — 열린 브라우저가 없어도 돈다
    if getattr(args, "stale", False):
        return action.run(args, state, state_f)
    # 뷰포트·규칙은 브라우저 없이도 적어 둘 수 있다 — 다음 open 에서 걸린다
    if action.needs == "state_offline":
        return action.run(args, state, state_f)

    if not state.get("cdp"):
        # 주 키는 실패에도 둔다 — json.load(...)["url"] 파이프가 KeyError 로 죽었다 (#931)
        return out({"ok": False, "code": "browser_not_open", "action": args.action, "url": None,
                    "error": "열린 브라우저가 없습니다",
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
        elif err.get("code") == "browser_hung":
            # 다음 web open 이 다시 붙지 않고 끄고 새로 띄우게 표시한다
            state[HUNG_MARK_KEY] = time.strftime("%Y-%m-%d %H:%M:%S")
            write_state(state_f, state)
        return out(err)
    pw, _browser, page = conn
    # 이 세션이 안 움직였는데 탭이 바뀌었으면 알린다 — 다른 세션과 같은 탭을 쓰는 중 (#878)
    tab_warning = drift_warning(page, state)
    # 마지막 사용 시각 — 오래 방치된 브라우저와 지금 쓰는 브라우저를 가른다 (#825)
    state["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_state(state_f, state)

    # 이 조작이 일으킨 요청 — 저장이 정말 서버로 갔는지 (#930)
    capture = RequestCapture().attach(page) if getattr(args, "capture_requests", False) else None
    try:
        try:
            payload = action.run(page, args, state)
        except Exception as e:
            payload = _action_failure(args, e, page, secret_value)
        if capture is not None and isinstance(payload, dict):
            payload["requests"] = capture.finish()
    finally:
        mark_tab(page, state)
        # 연결만 끊는다. browser.close()를 부르면 다음 호출이 붙을 곳이 없어진다.
        pw.stop()
    _save_tab_mark(state_f, state)
    if isinstance(payload, dict):
        attach_match_warning(payload)
    if tab_warning and isinstance(payload, dict):
        payload["tab_warning"] = tab_warning
    _attach_dialog_event(payload, state, state_f)
    # 로그인 입력이면 중간 화면 정책을 싣는다 (#905)
    if args.action == "type" and secret_value:
        with_login_policy(payload, getattr(args, "cred", None))
    elif args.action == "login":
        with_login_policy(payload, getattr(args, "login_cred", None))
    return out(payload)


def _action_failure(args, error: Exception, page, secret_value: str | None) -> dict:
    """동작 중 예외 > web_action_failed. 비밀값은 가리고, 선택자 문법 오류면 공통 안내를 붙인다 (#931)"""
    # 예외 문구에 입력값이 섞여 나올 수 있다 — 비밀값이면 가리고 내보낸다
    message = str(error)
    if secret_value:
        message = message.replace(secret_value, "***")
    payload = {"ok": False, "code": "web_action_failed", "action": args.action,
               "error": message[:400], "url": page.url if page else None,
               "next": "web shot  # 지금 화면이 무엇인지 먼저 봅니다"}
    if is_selector_syntax_error(message):
        payload.update({"selector_syntax_error": True, "hint": SELECTOR_SYNTAX_HINT,
                        "next": "web find --text <글자>  # 번호(ref)로 고르면 선택자를 짓지 않아도 된다"})
    return payload


def _save_tab_mark(state_f, state: dict) -> None:
    """탭 기록만 지금 파일에 합쳐 쓴다 — 동작 도중 다른 세션이 쓴 값(새 탭 등)을 덮지 않게."""
    fresh = read_state(state_f) if state_f.is_file() else {}
    if not fresh.get("cdp"):
        return
    fresh["tab_marks"] = {**(fresh.get("tab_marks") or {}), **(state.get("tab_marks") or {})}
    write_state(state_f, fresh)


def _attach_dialog_event(payload: dict, state: dict, state_f) -> None:
    """이번 호출 중에 뜬 대화상자를 결과에 싣고, 걸어 둔 처리를 썼으면 상태 파일에 남긴다."""
    event = state.pop(DIALOG_EVENT_KEY, None)
    if not event:
        return
    payload["dialog"] = event
    write_state(state_f, state)


COMMANDS = [Command(name="web", help="브라우저를 조작한다", run=cmd_web, configure=configure)]
