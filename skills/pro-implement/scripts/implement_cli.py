#!/usr/bin/env python3
"""implement_cli — implement skill 전용 CLI.

이 스킬은 산출물을 **쓰지 않고 읽는다.** plan·analyze 가 남긴 문서를 먼저 읽어야
같은 것을 두 번 설계하지 않는다.

서브커맨드: find-inputs

예전에는 SKILL.md 가 `docs/projectops/plan/` · `analyze/` 를 박아 놓고 스캔했다.
산출물 루트를 옮긴 팀에서는 **빈 폴더를 뒤지고 "계획 없음"으로 판단**했다 —
틀렸다는 신호가 없어 그대로 구현에 들어갔다 (#623).
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

# 구현 전에 읽어야 하는 산출물. 늘어나면 여기에만 추가한다.
_INPUT_SKILLS = ("plan", "analyze")


def cmd_find_inputs(args) -> int:
    import subprocess

    from common.paths import resolve_output_root

    try:
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return emit({"ok": False, "code": "git_not_found", "error": "git 저장소가 아닙니다"})

    base = resolve_output_root(root)
    inputs, found = {}, []
    for skill in _INPUT_SKILLS:
        d = base / skill
        files = sorted((f for f in d.glob("*.md") if f.is_file()),
                       key=lambda f: f.name, reverse=True) if d.is_dir() else []
        inputs[skill] = {
            "dir": str(d),
            "exists": d.is_dir(),
            "count": len(files),
            # 파일명이 `날짜_번호_제목` 이라 이름 역순이 곧 최신순이다
            "latest": str(files[0]) if files else None,
            "recent": [str(f) for f in files[:5]],
        }
        if files:
            found.append(f"{skill} {len(files)}개")

    return emit({
        "output_root": str(base),
        "inputs": inputs,
        "summary": ("구현 전에 읽을 산출물: " + " · ".join(found)) if found
                   else "plan·analyze 산출물이 없습니다",
        "next": ("각 `latest` 를 Read 로 읽고 시작하세요. 사용자가 특정 문서를 지정했으면 "
                 "그것을 우선합니다" if found else
                 "설계 문서가 없으므로 사용자에게 무엇을 구현할지 확인하거나 "
                 "`/pro-plan`·`/pro-analyze` 를 먼저 돌리세요"),
    })


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="implement_cli", description="implement skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fi = sub.add_parser("find-inputs", help="구현 전에 읽어야 할 plan·analyze 산출물")
    p_fi.set_defaults(func=cmd_find_inputs)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
