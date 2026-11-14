"""`web clipboard` — press a copy button, then save the host clipboard without printing it (#930).

Replaces reading values only exposed via a copy button (e.g. Play app signing fingerprints) with `pbcopy </dev/null; click; pbpaste`.
The value is saved to the same 0600 file as `web value`; the result carries only the length and a sha256 prefix.
It reads this computer's system clipboard — a headless browser's copy may not reach it, so use it with `--headed`.
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
