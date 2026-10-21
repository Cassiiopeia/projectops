"""`app` — 앱 화면을 찍고 · 띄우고 · 끄고 · 글자를 넣고 · 누르고 · 민다 · 위치·권한·푸시·딥링크를 건다.

동작 하나는 `actions/` 의 모듈 하나다. 플랫폼(Android·iOS)마다 다른 것은 `scripts/app_input.py` 의
백엔드가 전부 맡는다 — 새 플랫폼은 거기에 백엔드를 추가하고 이 폴더는 건드리지 않는다.
"""
from __future__ import annotations

import time

from pro_launch.commands.app import actions as _actions
from pro_launch.registry import Command, discover_actions
from pro_launch.runtime.context import MEMORY_CTX, project_root
from pro_launch.runtime.device_gate import gate_device_use
from pro_launch.runtime.shots import add_shot_args

ACTIONS = discover_actions(_actions)


def configure(p) -> None:
    # 여러 동작이 함께 쓰는 옵션. 한 동작만 쓰는 옵션은 그 동작의 configure 에 둔다
    p.add_argument("action", choices=sorted(ACTIONS))
    p.add_argument("--shot", default=None, help="tap·swipe·back·run: take a shot right after (name or path) — saves a separate shot call")
    p.add_argument("--root", default=".")
    p.add_argument("--device", default=None,
                   help="Android serial or iOS UDID. Default: $DEV → the only attached device")
    p.add_argument("--yes", action="store_true",
                   help="proceed even on a device held by another session (only after asking the user)")
    p.add_argument("--pkg", default=None, help="launch·terminate·relaunch·permission·push: package name / bundle ID (default: $PKG → device bind package)")
    add_shot_args(p)
    for action in ACTIONS.values():
        if action.configure:
            action.configure(p)


def cmd_app(args) -> int:
    MEMORY_CTX["root"] = project_root(args)
    # 동작이 결과에 elapsed_seconds 를 붙이는 기준점 (기기 고르기·도구 실행 전부 포함)
    args.started_monotonic = time.monotonic()
    action = ACTIONS.get(args.action, ACTIONS["launch"])
    # 소유 확인·기록은 여기 한 곳 (동작 선언 device_use)
    refusal = gate_device_use(action.device_use, args.device, str(MEMORY_CTX["root"]), bool(getattr(args, "yes", False)))
    if refusal is not None:
        return refusal
    return action.run(args)


COMMANDS = [Command(name="app",
                    help="Capture (shot), start/stop (launch·terminate·relaunch), type, tap, swipe and go back in an app. Several steps at once (run). "
                         "Location, permissions, push, deep links (location·permission·push·openurl)",
                    run=cmd_app, configure=configure)]
