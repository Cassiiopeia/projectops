"""Actions Secret 서브커맨드: secrets (list|set)."""
from __future__ import annotations

import os

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
                "summary": f"{args.owner}/{args.repo} secret {len(secrets)}개",
            })
        if args.sub == "set":
            if not args.name:
                return emit({"ok": False, "code": "missing_argument", "error": "name 필요"})
            value = os.environ.get("SECRET_VALUE")
            if value is None:
                return emit({
                    "ok": False, "code": "missing_secret_value",
                    "error": "SECRET_VALUE 환경변수에 값을 담아 호출하세요.",
                })
            result = api.set_secret(args.owner, args.repo, args.name, value, pat)
            return emit({**result, "summary": f"secret {args.name} 갱신 완료"})
        return emit({"ok": False, "code": "unknown_subcommand", "error": f"알 수 없음: {args.sub}"})
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


COMMANDS = [
    Command(name="secrets", help="Actions Secret 관리 (list|set)", run=cmd_secrets,
            configure=_configure_secrets),
]
