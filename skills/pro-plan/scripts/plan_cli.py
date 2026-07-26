#!/usr/bin/env python3
"""plan_cli — plan skill 전용 CLI.

산출물 md 출력 경로 계산.
서브커맨드: get-output-path

경로 규칙 자체는 Layer 1(`scripts/common/paths.py`)이 단일 소유한다.
이 파일은 그 규칙을 호출만 한다 — 스킬마다 규칙이 갈라지지 않게 하기 위함이다 (#525).
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
    return emit(resolve_output_path(args.skill_id, args.title))


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="plan_cli", description="plan skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gop = sub.add_parser("get-output-path", help="구현 계획 출력 경로")
    p_gop.add_argument("skill_id", nargs="?", default="plan")
    p_gop.add_argument("--title")
    p_gop.set_defaults(func=cmd_get_output_path)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
