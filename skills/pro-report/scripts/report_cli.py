#!/usr/bin/env python3
"""report_cli — report skill 전용 CLI.

구현 보고서 출력 경로 계산 + PR 댓글 포스팅.
서브커맨드: get-output-path, add-comment

사용법:
    cd skills/pro-report/scripts
    python report_cli.py <subcommand> [args]
"""
from __future__ import annotations

import os
import sys
import subprocess
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402
from common.config import get_github_pat  # noqa: E402
from common.gh_client import GitHubAPIError, add_comment  # noqa: E402
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402


def _resolve_output_path(skill_id: str, forced_title: str | None) -> dict:
    """경로 규칙은 Layer 1(common/paths.py)이 단일 소유 — 여기서 재구현하지 않는다 (#525)."""
    from common.paths import resolve_output_path
    return resolve_output_path(skill_id, forced_title)



def cmd_get_output_path(args) -> int:
    result = _resolve_output_path(args.skill_id, args.title)
    return emit(result)


def cmd_add_comment(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    body_path = Path(args.body_file)
    if not body_path.exists():
        return emit({"ok": False, "code": "body_file_not_found", "error": f"{args.body_file} 없음"})
    body = body_path.read_text(encoding="utf-8")
    try:
        result = add_comment(args.owner, args.repo, args.number, body, pat)
        return emit({**result, "summary": f"#{args.number}에 댓글 추가"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="report_cli", description="report skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gop = sub.add_parser("get-output-path", help="보고서 출력 경로")
    p_gop.add_argument("skill_id", nargs="?", default="report")
    p_gop.add_argument("--title")
    p_gop.set_defaults(func=cmd_get_output_path)

    p_ac = sub.add_parser("add-comment", help="이슈 댓글 추가 (보고서 포스팅)")
    p_ac.add_argument("owner")
    p_ac.add_argument("repo")
    p_ac.add_argument("number", type=int)
    p_ac.add_argument("body_file")
    p_ac.set_defaults(func=cmd_add_comment)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
