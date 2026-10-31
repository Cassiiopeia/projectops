"""token: Figma 토큰 상태 보기 · 등록 (값은 어디에도 출력하지 않는다)"""
from __future__ import annotations

import getpass
import os
import sys

from common.emit import emit
from figma_tools.figma_auth import TOKEN_ENV_NAME, fetch_json, find_token, save_token


def _read_token(args) -> tuple[str | None, dict | None]:
    if args.from_env:
        value = os.environ.get(args.from_env, "").strip()
        if not value:
            return None, {"ok": False, "code": "env_empty", "error": f"Environment variable {args.from_env} is empty or unset"}
        return value, None
    if not sys.stdin.isatty():
        # 채팅이나 인자로 토큰을 받으면 대화 기록·셸 기록에 남는다
        return None, {"ok": False, "code": "no_tty",
                      "error": "Hidden input needs a terminal",
                      "hint": f"Run it in your own terminal, or put the token in an environment variable "
                              f"and use --from-env NAME (for example {TOKEN_ENV_NAME})"}
    return getpass.getpass("Figma personal access token (hidden): ").strip(), None


def cmd_token(args) -> int:
    if not (args.prompt or args.from_env):
        _token, source = find_token()
        return emit({"configured": source is not None, "source": source,
                     "summary": f"Figma token found ({source})" if source else "No Figma token found",
                     "next": "check-fresh --dump <dump>" if source else "token --prompt"})
    token, err = _read_token(args)
    if err:
        return emit(err)
    if not token:
        return emit({"ok": False, "code": "empty_token", "error": "No token was entered"})

    warnings = []
    check = fetch_json("/me", token)
    if check.get("ok") and check["status"] in (401, 403):
        return emit({"ok": False, "code": "figma_token_rejected",
                     "error": "Figma rejected this token; nothing was saved"})
    if not check.get("ok") or check["status"] != 200:
        warnings.append({"code": "not_verified", "message": "Could not verify the token against Figma; saved as is"})
    name, save_err = save_token(token, args.name)
    if save_err:
        return emit(save_err)
    return emit({"saved_as": name, "warnings": warnings,
                 "summary": f"Saved the Figma token as credential '{name}'",
                 "next": "check-fresh --dump <dump>"})
