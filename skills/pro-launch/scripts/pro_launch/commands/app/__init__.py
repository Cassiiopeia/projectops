"""`app` — 앱 화면을 찍고 · 띄우고 · 글자를 넣고 · 누르고 · 민다.

동작 하나는 `actions/` 의 모듈 하나다. 플랫폼(Android·iOS)마다 다른 것은 `scripts/app_input.py` 의
백엔드가 전부 맡는다 — 새 플랫폼은 거기에 백엔드를 추가하고 이 폴더는 건드리지 않는다.
"""
from __future__ import annotations

from pro_launch.commands.app import actions as _actions
from pro_launch.registry import Command, discover_actions
from pro_launch.runtime.context import MEMORY_CTX, project_root
from pro_launch.runtime.shots import add_shot_args

ACTIONS = discover_actions(_actions)


def configure(p) -> None:
    # 여러 동작이 함께 쓰는 옵션. 한 동작만 쓰는 옵션은 그 동작의 configure 에 둔다
    p.add_argument("action", choices=sorted(ACTIONS))
    p.add_argument("--shot", default=None, help="tap·swipe: 끝나면 바로 찍는다 (이름 또는 경로) — 확인용 shot 호출을 아낀다")
    p.add_argument("--root", default=".")
    p.add_argument("--device", default=None,
                   help="Android 시리얼 또는 iOS UDID. 없으면 $DEV → 붙은 기기가 한 대면 그것")
    p.add_argument("--pkg", default=None, help="launch: 패키지명·번들 ID (없으면 $PKG)")
    add_shot_args(p)
    for action in ACTIONS.values():
        if action.configure:
            action.configure(p)


def cmd_app(args) -> int:
    MEMORY_CTX["root"] = project_root(args)
    return ACTIONS.get(args.action, ACTIONS["launch"]).run(args)


COMMANDS = [Command(name="app",
                    help="앱 화면을 찍고(shot) 띄우고(launch) 글자를 넣고(type) 누르고(tap) 민다(swipe)",
                    run=cmd_app, configure=configure)]
