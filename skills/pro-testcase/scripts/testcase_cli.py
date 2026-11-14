#!/usr/bin/env python3
"""testcase_cli — CLI for the testcase skill.

Computes the output md path.
Subcommands: get-output-path

The path rules themselves are owned solely by Layer 1 (`scripts/common/paths.py`).
This file only calls them — so rules never diverge per skill (#525).
If SKILL.md assembled the path itself, teams that moved the output root would **write silently to the wrong place** (#623).
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402


def cmd_get_output_path(args) -> int:
    from common.paths import resolve_output_path
    return emit(resolve_output_path(args.skill_id, args.title, root=args.root, issue=args.issue))


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="testcase_cli", description="testcase skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gop = sub.add_parser("get-output-path", help="Output path for the QA test case document")
    p_gop.add_argument("skill_id", nargs="?", default="testcase")
    p_gop.add_argument("--title")
    from common.paths import add_root_and_issue_args
    add_root_and_issue_args(p_gop)
    p_gop.set_defaults(func=cmd_get_output_path)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
