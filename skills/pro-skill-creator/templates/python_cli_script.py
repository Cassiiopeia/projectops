#!/usr/bin/env python3
"""<scope>_cli — <skill name> 전용 CLI (projectops 3-layer 표준 골격).

이 파일은 신규 skill 생성 시 복사하는 표준 골격이다.
3-layer 아키텍처 Layer 2 (`skills/<skill>/scripts/<scope>_cli.py`).

표준 (`skills/references/common-rules.md` §"skill별 py 분산 호출" 참조):
- Layer 1 (`scripts/common/`): 공유 인프라 (gh_client, config, paths, title 등)
- Layer 2 (이 파일): skill 1개 = py 1개 = argparse 서브커맨드
- Layer 3 (SKILL.md): self-contained 5줄 Bash 호출

사용법:
    1. 이 파일을 skills/suh-<new>/scripts/<scope>_cli.py 로 복사.
    2. prog 이름 + 서브커맨드를 신규 skill에 맞게 교체.
    3. 공유 로직은 `from common.<module> import ...` 형태로 import (재작성 금지).
    4. SKILL.md 코드블록은 표준 5줄 패턴 사용.

호출 예 (SKILL.md):
    PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
    [ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
    cd "$PROJECT_ROOT/skills/<skill>/scripts" || exit 1
    PYTHONIOENCODING=utf-8 "$PYTHON" <scope>_cli.py <subcommand> [args]

출력: 모든 서브커맨드는 stdout으로 MCP-style JSON 출력 (4필드 강제: ok/code/summary/next).
출력 문자열(summary·error·next·argparse help)은 영어로 작성 — 주석·docstring은 한국어 (#769).
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

# Bootstrap — scripts/common import 가능하게 sys.path 조작 (cwd 무관 동작)
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]  # skills/<x>/scripts/<x>_cli.py → 3 up = project root
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402

# 신규 skill이 공유 로직 import:
# from common.gh_client import GitHubAPIError, get_issue  # noqa: E402
# from common.config import get_github_pat  # noqa: E402


# =========================================================================
# Subcommand handlers
# =========================================================================

def cmd_example(args) -> int:
    """예시 서브커맨드 — 인자 그대로 echo한다.

    실제 skill에서는 이 함수를 도메인 로직으로 교체한다:
        - common.gh_client import 하여 GitHub API 호출
        - common.config get_github_pat() 로 PAT 자동 로드
        - 결과 dict를 emit()로 반환 (4필드 자동 보장)
    """
    return emit({
        "input": args.text,
        "summary": f"Input: {args.text}",
        # 필요 시 next 힌트 추가:
        # "next": f"another-cmd {args.text}",
    })


# =========================================================================
# argparse setup
# =========================================================================

def build_parser() -> argparse.ArgumentParser:
    """argparse subparser 정의. 신규 서브커맨드 등록 시 여기에 추가."""
    parser = argparse.ArgumentParser(
        prog="<scope>_cli",
        description="<skill name> skill CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ex = sub.add_parser("example", help="Example subcommand")
    p_ex.add_argument("text")
    p_ex.set_defaults(func=cmd_example)

    # 신규 서브커맨드 추가 패턴:
    # p_new = sub.add_parser("new-cmd", help="What the subcommand does")
    # p_new.add_argument("owner")
    # p_new.add_argument("repo")
    # p_new.add_argument("--state", choices=["open", "closed"], default="open")
    # p_new.set_defaults(func=cmd_new)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
