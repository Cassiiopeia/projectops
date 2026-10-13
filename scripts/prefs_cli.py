#!/usr/bin/env python3
"""prefs_cli — 모든 스킬이 공유하는 개인 설정 조회 CLI.

사용: python scripts/prefs_cli.py resolve --skill pro-report [--repo owner/repo]
--repo 를 생략하면 현재 디렉터리의 origin remote 로 레포 층을 찾는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402
from common.emit import emit  # noqa: E402
from common.preferences import detect_repo, resolve  # noqa: E402


def cmd_resolve(args) -> int:
    owner = repo = None
    if args.repo:
        if "/" not in args.repo:
            return emit({"ok": False, "code": "bad_repo", "error": "--repo 는 owner/repo 형식"})
        owner, repo = args.repo.split("/", 1)
    else:
        owner, repo = detect_repo()
    result = resolve(args.skill, owner, repo, load=True)
    keys = ", ".join(sorted(result["values"])) or "없음(기본값)"
    return emit({**result, "repo": f"{owner}/{repo}" if owner else None,
                 "summary": f"{args.skill} 설정: {keys}"})


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="prefs_cli", description="개인 설정(preferences) 조회")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("resolve", help="스킬 하나의 최종 설정과 출처")
    p.add_argument("--skill", required=True)
    p.add_argument("--repo", default=None)
    p.set_defaults(func=cmd_resolve)
    return parser


if __name__ == "__main__":
    sys.exit(run_cli(build_parser()))
