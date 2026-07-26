#!/usr/bin/env python3
"""review_cli — review skill 전용 CLI.

코드 리뷰 결과 출력 경로 계산.
서브커맨드: get-output-path
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402


def cmd_get_output_path(args) -> int:
    # 경로 규칙은 Layer 1(common/paths.py)이 단일 소유 — 여기서 재구현하지 않는다 (#525)
    from common.paths import resolve_output_path
    return emit(resolve_output_path(args.skill_id, args.title))

def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="review_cli", description="review skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gop = sub.add_parser("get-output-path", help="리뷰 결과 출력 경로")
    p_gop.add_argument("skill_id", nargs="?", default="review")
    p_gop.add_argument("--title")
    p_gop.set_defaults(func=cmd_get_output_path)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
