"""`web clipboard` — 복사 버튼을 누른 뒤 호스트 클립보드를 출력하지 않고 저장한다 (#930).

Play 앱 서명 지문처럼 복사 버튼으로만 나오는 값을 `pbcopy </dev/null; click; pbpaste` 로 읽던 것을 대신한다.
값은 `web value` 와 같은 0600 파일에 저장하고 결과에는 길이 · sha256 앞자리만 싣는다.
읽는 곳은 이 컴퓨터의 시스템 클립보드다 — headless 브라우저의 복사는 시스템 클립보드에 닿지 않을 수 있어 `--headed` 에서 쓴다.
"""
from __future__ import annotations

import hashlib

from pro_launch.commands.web.saved_values import (HASH_PREFIX_CHARS, invalid_name_failure, is_valid_env_name,
                                                  save_value, saved_next)
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import read_system_clipboard


def execute(args) -> int:
    if args.save_env and not is_valid_env_name(args.save_env):
        return out(invalid_name_failure("clipboard", args.save_env))
    value, reason = read_system_clipboard()
    if value is None:
        return out({"ok": False, "code": "clipboard_unreadable", "action": "clipboard", "error": reason,
                    "next": "web value --selector <값이 보이는 칸> --save-env NAME  # 화면에 값이 있으면 이쪽"})
    value = value.strip("\r\n")
    if not value:
        return out({"ok": False, "code": "clipboard_empty", "action": "clipboard", "length": 0,
                    "error": "클립보드가 비어 있습니다 (복사가 안 됐다)",
                    "hint": "headless 브라우저의 복사는 시스템 클립보드에 닿지 않는다 — web open --headed 로 다시 열고 복사 버튼을 누른다",
                    "next": "web click --ref <복사 버튼>  # 누른 뒤 다시 web clipboard"})
    if not args.save_env:
        return out({"action": "clipboard", "length": len(value),
                    "sha256_prefix": hashlib.sha256(value.encode("utf-8")).hexdigest()[:HASH_PREFIX_CHARS],
                    "summary": f"클립보드 {len(value)}자 (저장하지 않음)",
                    "next": "web clipboard --save-env NAME  # 값을 출력 없이 저장한다"})
    saved = save_value(project_root(args), args.save_env, value)
    return out({"action": "clipboard", **saved,
                "summary": f"클립보드 {len(value)}자를 {args.save_env} 로 저장했다 (출력하지 않음)",
                "next": saved_next(args.save_env)})


def configure(p) -> None:
    p.add_argument("--save-env", dest="save_env", default=None,
                   help="클립보드 값을 이 이름으로 저장한다 (출력하지 않음). web type --text-env 이름 으로 다시 쓴다")


ACTION = Action(name="clipboard", needs="nothing", run=execute, configure=configure, options=(),
                help="복사 버튼을 누른 뒤 클립보드 값을 출력 없이 저장한다 (길이 · 해시만 보여 준다)",
                example="web clipboard --save-env SHA1_FINGERPRINT")
