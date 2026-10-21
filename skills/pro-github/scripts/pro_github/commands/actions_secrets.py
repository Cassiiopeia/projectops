"""Actions Secret 서브커맨드: secrets (list|set)."""
from __future__ import annotations

import os
from pathlib import Path

from common.emit import emit
from common.gh_client import GitHubAPIError, PyNaClMissingError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat


def cmd_secrets(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        if args.sub == "list":
            secrets = api.list_secrets(args.owner, args.repo, pat)
            return emit({
                "count": len(secrets),
                "secrets": secrets,
                "summary": f"{args.owner}/{args.repo}: {len(secrets)} secret(s)",
            })
        if args.sub == "set":
            if not args.name:
                return emit({"ok": False, "code": "missing_argument", "error": "name is required"})
            value = os.environ.get("SECRET_VALUE")
            if args.value_file:
                # 여러 줄 값(.env 통째로 등)은 파일로: 셸 이스케이프 없이 그대로 읽는다 (#939)
                try:
                    value = Path(args.value_file).read_text(encoding="utf-8")
                except OSError as error:
                    return emit({"ok": False, "code": "value_file_not_found", "error": f"{args.value_file}: {error}"})
            if value is None:
                return emit({
                    "ok": False, "code": "missing_secret_value",
                    "error": "put the value in the SECRET_VALUE environment variable or pass a file with --value-file.",
                })
            result = api.set_secret(args.owner, args.repo, args.name, value, pat)
            return emit({**result, "summary": f"updated secret {args.name}"})
        return emit({"ok": False, "code": "unknown_subcommand", "error": f"unknown: {args.sub}"})
    except PyNaClMissingError as e:
        return emit({"ok": False, "code": e.code, "error": str(e), "hint": "pip install PyNaCl"})
    except GitHubAPIError as e:
        return api_error(e)


# ── 인자 ──

def _configure_secrets(parser) -> None:
    parser.add_argument("sub", choices=["list", "set"])
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("name", nargs="?")
    parser.add_argument("--value-file", dest="value_file", default=None,
                        help="set: file holding the value (instead of SECRET_VALUE; may span lines)")


COMMANDS = [
    Command(name="secrets", help="manage Actions secrets (list|set)", run=cmd_secrets,
            configure=_configure_secrets),
]
