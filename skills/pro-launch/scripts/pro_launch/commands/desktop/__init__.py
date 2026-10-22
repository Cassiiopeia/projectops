"""`desktop` — PC 화면에 뜬 프로그램(설치 마법사 · OS 대화상자 · 데스크톱 앱)을 읽고 누른다 (#985).

브라우저 페이지 안은 `web`, 에뮬레이터·시뮬레이터는 `app` 이 맡는다. 여기는 그 밖의 창이다.

안전 관문은 이 파일 한 곳에 있다 (동작 선언 `device_use`).
    read    의존성만 본다 — 창 목록 · 구조 · 캡처 · 대기
    mutate  + 보안 화면(UAC·잠금) 아님 + 이 세션이 입력 세션을 쥠 + 일시정지 아님
    none    동작이 직접 판단한다 (setup · doctor · session)
OS 차이는 전부 `scripts/desktop_input.py` 의 백엔드가 맡는다. 동작을 추가해도 이 파일은 고치지 않는다.
"""
from __future__ import annotations

import argparse

from pro_launch.commands.desktop import actions as _actions
from pro_launch.commands.desktop.common import load_backend
from pro_launch.commands.desktop.options import ALWAYS_OPTIONS, MAX_TIMEOUT_SECONDS, SHARED_OPTIONS
from pro_launch.registry import Command, action_usage_lines, add_action_parsers, discover_actions
from pro_launch.runtime import desktop_state
from pro_launch.runtime.context import MEMORY_CTX, project_root
from pro_launch.runtime.output import out, set_area

ACTIONS = discover_actions(_actions)


def configure(p) -> None:
    add_action_parsers(p, ACTIONS, SHARED_OPTIONS, always=ALWAYS_OPTIONS)
    p.formatter_class = argparse.RawDescriptionHelpFormatter
    p.description = "Drive programs on this computer's screen, one action per call — options per action: desktop <action> --help"
    p.epilog = "Options per action:\n" + "\n".join(action_usage_lines(p))


def input_gate(be) -> dict | None:
    """화면을 바꾸는 동작 전에. 막아야 하면 실패 결과, 지나가면 None."""
    ready = be.readiness()
    if ready.get("secure_desktop") or ready.get("consent_prompt"):
        return {"ok": False, "code": "needs_user", "reason": "secure_desktop",
                "error": "A security prompt (UAC, sign-in, Ctrl+Alt+Del) is in front. Only a person can answer it",
                "ask_user": "Please answer the security prompt on the screen, then tell me when it is done",
                "next": "desktop windows  # after the user says it is done"}
    if ready.get("locked"):
        return {"ok": False, "code": "screen_locked", "error": "The screen is locked",
                "ask_user": "Please unlock the screen, then tell me when it is done"}
    missing = [k for k, granted in (ready.get("permissions") or {}).items() if not granted]
    if missing:
        return {"ok": False, "code": "permission_missing", "missing": missing,
                "error": f"macOS has not granted {', '.join(missing)} to this terminal app",
                "next": "desktop doctor  # shows where to grant it"}
    holder = desktop_state.current_holder()
    mine = desktop_state.my_session()
    if mine is None:
        if holder:
            return {"ok": False, "code": "desktop_busy", "holder": holder.get("session"),
                    "purpose": holder.get("purpose"),
                    "error": "Another session is using this computer's keyboard and mouse",
                    "next": "desktop session status  # wait, or ask the user"}
        return {"ok": False, "code": "desktop_session_required",
                "error": "Start an input session first — it tells the user this session will use the keyboard and mouse",
                "next": "desktop session start --purpose \"<why>\""}
    if mine.get("paused"):
        return {"ok": False, "code": "user_interrupted",
                "error": "The input session is paused because the user moved the mouse",
                "ask_user": "You moved the mouse while I was working. May I continue?",
                "next": "desktop session resume  # only after the user agrees"}
    return None


def cmd_desktop(args) -> int:
    MEMORY_CTX["root"] = project_root(args)
    set_area("desktop", MEMORY_CTX["root"])
    if getattr(args, "timeout", None) and args.timeout > MAX_TIMEOUT_SECONDS:
        return out({"ok": False, "code": "timeout_too_large",
                    "error": f"--timeout is in seconds (max {MAX_TIMEOUT_SECONDS})"})
    action = ACTIONS[args.action]
    args.backend = None
    if action.device_use in ("read", "mutate"):
        be, failure = load_backend()
        if failure:
            return out(failure)
        if action.device_use == "mutate":
            refusal = input_gate(be)
            if refusal:
                return out({**refusal, "platform": be.name, "action": args.action})
        args.backend = be
    return action.run(args)


COMMANDS = [Command(name="desktop",
                    help="Drive programs on this computer's screen (installers, OS dialogs, desktop apps): "
                         "windows, tree, find, click, type, press, shot, wait — input only inside a session",
                    run=cmd_desktop, configure=configure)]
