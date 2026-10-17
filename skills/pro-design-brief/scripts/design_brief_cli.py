#!/usr/bin/env python3
"""design_brief_cli — pro-design-brief 전용 CLI (projectops 3-layer 표준, Layer 2, #634).

디자이너에게 넘길 요청서(보드)를 조립한다. **판단은 agent, 스크립트는 실행과 기록만** 한다 —
상태 목록·대안·문구 후보를 고르는 것은 agent 이고, 여기서는 설정을 풀고 보드를 조립하고
기계적으로 검사할 수 있는 것만 검사한다.

서브커맨드:
    config show|set   design_brief 설정 해석(일치 항목 · 출처) / 저장
    get-output-path   이번 요청서의 산출물 자리
    board             데이터 JSON → 보드 HTML (+ --png 면 주제별 PNG)
    copy-lint         문구 후보의 기계적 검사 (em dash · 가운뎃점 · 금지어 · 번역투)
    ascii             박스 문자 와이어 (한글 폭 보정)

출력: MCP-style JSON (ok/code/summary/next 4필드 보장).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

# 구현은 같은 폴더의 pro_design_brief 패키지에 있다 (공용 common 경로는 패키지가 맞춘다)
_HERE = Path(__file__).resolve()
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

import pro_design_brief  # noqa: E402,F401  (common import 경로를 맞춘다)
from common.emit import emit  # noqa: E402

from pro_design_brief.ascii_wire import cmd_ascii  # noqa: E402
from pro_design_brief.board import cmd_board  # noqa: E402
from pro_design_brief.config import cmd_config  # noqa: E402
from pro_design_brief.copy_lint import cmd_copy_lint  # noqa: E402
from pro_design_brief.output_path import cmd_output_path  # noqa: E402
from pro_design_brief.settings import DESTINATIONS  # noqa: E402

# 테스트가 design_brief_cli.<이름> 으로 직접 쓰는 함수·값 재노출
from pro_design_brief.ascii_wire import _fit, text_width  # noqa: E402,F401
from pro_design_brief.board_capture import _png_width, _require_playwright  # noqa: E402,F401
from pro_design_brief.board_html import render_html  # noqa: E402,F401
from pro_design_brief.board_markdown import preflight, render_markdown  # noqa: E402,F401
from pro_design_brief.config import _designer_from_templates, resolve_config  # noqa: E402,F401
from pro_design_brief.copy_lint import _banned_hit  # noqa: E402,F401
from pro_design_brief.settings import MAX_PNG_WIDTH  # noqa: E402,F401


# =========================================================================
# 인자
# =========================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="design_brief_cli", description="디자인 요청서를 조립한다")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("config", help="design_brief 설정 해석 / 저장")
    p.add_argument("action", choices=["show", "set"])
    p.add_argument("--root", default=".")
    p.add_argument("--scope", choices=["project", "default"], default="project",
                   help="set: 이 레포만(project) 또는 모든 레포 기본값(default)")
    p.add_argument("--destination", default=None, help=f"set: {' · '.join(DESTINATIONS)}")
    p.add_argument("--designer", default=None, help="set: 디자이너 GitHub 아이디 또는 이름")
    p.add_argument("--auto-approve", choices=["true", "false"], default=None,
                   help="set: 게시 전 확인을 생략할지")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("get-output-path", help="이번 요청서의 산출물 자리")
    p.add_argument("--title", default=None)
    p.set_defaults(func=cmd_output_path)

    p = sub.add_parser("board", help="데이터 JSON → 보드 HTML (+ 주제별 PNG)")
    p.add_argument("--data", required=True, help="보드 데이터 JSON (SKILL.md 의 형식)")
    p.add_argument("--out", required=True, help="보드를 쓸 폴더")
    p.add_argument("--png", action="store_true", help="주제별 PNG 도 만든다 (pro-launch 의 Chromium)")
    p.add_argument("--scale", type=int, default=2, help="PNG 배율 (기본 2 — 폭 약 2900px)")
    p.add_argument("--md", action="store_true", help="markdown 출력용 brief.md 도 만든다 (PNG 링크 포함)")
    p.add_argument("--strict", action="store_true",
                   help="preflight 경고가 있으면 ok:false — 게시 직전에 쓴다")
    p.set_defaults(func=cmd_board)

    p = sub.add_parser("copy-lint", help="문구 후보의 기계적 검사")
    p.add_argument("--file", required=True, help="문구표 JSON (보드 데이터의 copy 배열 또는 보드 데이터 전체)")
    p.add_argument("--banned", default=None, help="쓰지 않기로 한 말 — 파일(한 줄에 하나) 또는 쉼표 목록")
    p.set_defaults(func=cmd_copy_lint)

    p = sub.add_parser("ascii", help="박스 문자 와이어 (한글 폭 보정)")
    p.add_argument("--spec", required=True, help="와이어 JSON 파일 또는 JSON 문자열")
    p.add_argument("--out", default=None, help="저장할 파일")
    p.set_defaults(func=cmd_ascii)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    err = io.StringIO()
    try:
        # argparse 가 stderr 로 쓰는 원인 문구를 error 에 싣는다 (에이전트는 JSON 만 읽는다)
        with contextlib.redirect_stderr(err):
            args = parser.parse_args(argv)
    except SystemExit as e:
        if e.code in (0, None):
            raise
        sys.stderr.write(err.getvalue())
        reason = err.getvalue().strip().splitlines()[-1] if err.getvalue().strip() else ""
        return emit({"ok": False, "code": "bad_args", "error": f"인자가 올바르지 않습니다: {reason}",
                     "next": "design_brief_cli.py <서브커맨드> --help"})
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
