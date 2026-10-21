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
    rewrite-images    업로드 결과로 md 의 로컬 그림 경로 > URL (이슈 본문용)

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
from pro_design_brief.image_links import cmd_rewrite_images  # noqa: E402
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
    parser = argparse.ArgumentParser(prog="design_brief_cli", description="Assemble a design request (brief) for a designer")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("config", help="Resolve / save the design_brief settings")
    p.add_argument("action", choices=["show", "set"])
    p.add_argument("--root", default=".")
    p.add_argument("--scope", choices=["project", "default"], default="project",
                   help="set: this repo only (project) or the default for all repos (default)")
    p.add_argument("--destination", default=None, help=f"set: {' · '.join(DESTINATIONS)}")
    p.add_argument("--designer", default=None, help="set: the designer's GitHub ID or name")
    p.add_argument("--auto-approve", choices=["true", "false"], default=None,
                   help="set: whether to skip the confirmation before posting")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("get-output-path", help="Output location for this request")
    p.add_argument("--title", default=None)
    p.set_defaults(func=cmd_output_path)

    p = sub.add_parser("board", help="Data JSON → board HTML (+ one PNG per topic)")
    p.add_argument("--data", required=True, help="Board data JSON (format in SKILL.md)")
    p.add_argument("--out", required=True, help="Folder to write the board into")
    p.add_argument("--png", action="store_true", help="Also render one PNG per topic (pro-launch Chromium)")
    p.add_argument("--scale", type=int, default=2, help="PNG scale factor (default 2, about 2900px wide)")
    p.add_argument("--md", action="store_true", help="Also write brief.md for markdown output (with PNG links)")
    p.add_argument("--strict", action="store_true",
                   help="Return ok:false when there are preflight warnings (use right before posting)")
    p.set_defaults(func=cmd_board)

    p = sub.add_parser("copy-lint", help="Mechanical check of copy candidates")
    p.add_argument("--file", required=True, help="Copy table JSON (the copy array of the board data, or the whole board data)")
    p.add_argument("--banned", default=None, help="Banned words: a file (one per line) or a comma-separated list")
    p.set_defaults(func=cmd_copy_lint)

    p = sub.add_parser("ascii", help="Box-drawing wireframe (corrects the width of Korean/full-width characters)")
    p.add_argument("--spec", required=True, help="Wireframe JSON file or JSON string")
    p.add_argument("--out", default=None, help="File to save to")
    p.set_defaults(func=cmd_ascii)

    p = sub.add_parser("rewrite-images", help="Replace local image paths in an md with the uploaded URLs")
    p.add_argument("--md", required=True, help="md whose image paths to replace (e.g. board/brief.md)")
    p.add_argument("--uploads", required=True, action="append",
                   help="upload-image output JSON file or {local_path: url} JSON (repeatable)")
    p.add_argument("--out", default=None, help="Output file (default: <md name>.issue.md; the original md is left as is)")
    p.set_defaults(func=cmd_rewrite_images)
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
        return emit({"ok": False, "code": "bad_args", "error": f"Invalid arguments: {reason}",
                     "next": "design_brief_cli.py <subcommand> --help"})
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
