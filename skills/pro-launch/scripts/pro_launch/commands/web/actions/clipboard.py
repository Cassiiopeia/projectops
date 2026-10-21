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
                    "next": "web value --selector <box showing the value> --save-env NAME  # use this if the value is on screen"})
    value = value.strip("\r\n")
    if not value:
        return out({"ok": False, "code": "clipboard_empty", "action": "clipboard", "length": 0,
                    "error": "The clipboard is empty (nothing was copied)",
                    "hint": "Copying in a headless browser does not reach the system clipboard — reopen with web open --headed and press the copy button",
                    "next": "web click --ref <copy button>  # then run web clipboard again"})
    if not args.save_env:
        return out({"action": "clipboard", "length": len(value),
                    "sha256_prefix": hashlib.sha256(value.encode("utf-8")).hexdigest()[:HASH_PREFIX_CHARS],
                    "summary": f"Clipboard holds {len(value)} chars (not saved)",
                    "next": "web clipboard --save-env NAME  # save the value without printing it"})
    saved = save_value(project_root(args), args.save_env, value)
    return out({"action": "clipboard", **saved,
                "summary": f"Saved {len(value)} clipboard chars as {args.save_env} (not printed)",
                "next": saved_next(args.save_env)})


def configure(p) -> None:
    p.add_argument("--save-env", dest="save_env", default=None,
                   help="Save the clipboard value under this name (not printed). Reuse it with web type --text-env NAME")


ACTION = Action(name="clipboard", needs="nothing", run=execute, configure=configure, options=(),
                help="After pressing a copy button, save the clipboard value without printing it (shows only length · hash)",
                example="web clipboard --save-env SHA1_FINGERPRINT")
