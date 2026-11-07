#!/usr/bin/env python3
"""ui_design_cli — pro-ui-design 전용 CLI (projectops 3-layer 표준, Layer 2, #634).

시안을 로컬에 띄워 고르고, 안 되면 디자이너에게 넘긴다. **판단은 agent, 스크립트는 실행과 기록만** 한다 —
시안 내용 · 상태 목록 · 대안 · 문구 후보를 만드는 것은 agent 이고, 여기서는 서버를 띄우고 사실을 모으고
기계적으로 검사할 수 있는 것만 검사한다.

서브커맨드:
    start · status · stop · choices   로컬 시안 세션과 서버, 클릭 기록
    tokens · check                    디자인 후보 파일 찾기, 시안 검사
    capture                           시안 > PNG, 단계 실행 > GIF
    decide · decision                 결정 기록 저장과 조회
    config show|set|options           설정 해석(일치 항목 · 출처) / 저장 / 옵션 표
    get-output-path                   이번 요청서의 산출물 자리
    board                             데이터 JSON > 보드 HTML (+ --png 면 주제별 PNG)
    copy-lint                         문구 후보의 기계적 검사 (em dash · 가운뎃점 · 금지어 · 번역투)
    ascii                             박스 문자 와이어 (한글 폭 보정)
    rewrite-images                    업로드 결과로 md 의 로컬 그림 경로 > URL (이슈 본문용)

출력: MCP-style JSON (ok/code/summary/next 4필드 보장).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

# 구현은 같은 폴더의 pro_ui_design 패키지에 있다 (공용 common 경로는 패키지가 맞춘다)
_HERE = Path(__file__).resolve()
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

import pro_ui_design  # noqa: E402,F401  (common import 경로를 맞춘다)
from common.emit import emit  # noqa: E402

from pro_ui_design.ascii_wire import cmd_ascii  # noqa: E402
from pro_ui_design.board import cmd_board  # noqa: E402
from pro_ui_design.capture import cmd_capture  # noqa: E402
from pro_ui_design.check import cmd_check  # noqa: E402
from pro_ui_design.config import cmd_config  # noqa: E402
from pro_ui_design.copy_lint import cmd_copy_lint  # noqa: E402
from pro_ui_design.decision import cmd_decide, cmd_decision  # noqa: E402
from pro_ui_design.image_links import cmd_rewrite_images  # noqa: E402
from pro_ui_design.output_path import cmd_output_path  # noqa: E402
from pro_ui_design.session_commands import cmd_choices, cmd_start, cmd_status, cmd_stop  # noqa: E402
from pro_ui_design.settings import DESTINATIONS  # noqa: E402
from pro_ui_design.tokens import cmd_tokens  # noqa: E402

# 테스트가 ui_design_cli.<이름> 으로 직접 쓰는 함수·값 재노출
from pro_ui_design.ascii_wire import _fit, text_width  # noqa: E402,F401
from pro_ui_design.board_capture import _png_width, _require_playwright  # noqa: E402,F401
from pro_ui_design.board_html import render_html  # noqa: E402,F401
from pro_ui_design.board_markdown import preflight, render_markdown  # noqa: E402,F401
from pro_ui_design.config import _designer_from_templates, resolve_config  # noqa: E402,F401
from pro_ui_design.copy_lint import _banned_hit  # noqa: E402,F401
from pro_ui_design.settings import MAX_PNG_WIDTH  # noqa: E402,F401


# =========================================================================
# 인자
# =========================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ui_design_cli", description="See and pick UI mockups locally; assemble a design request for a designer")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("config", help="Resolve / save the settings, or list every option")
    p.add_argument("action", choices=["show", "set", "options"])
    p.add_argument("--root", default=".")
    p.add_argument("--scope", choices=["project", "default"], default="project",
                   help="set: this repo only (project) or the default for all repos (default)")
    p.add_argument("--destination", default=None, help=f"set: {' · '.join(DESTINATIONS)}")
    p.add_argument("--designer", default=None, help="set: the designer's GitHub ID or name")
    p.add_argument("--auto-approve", choices=["true", "false"], default=None,
                   help="set: whether to skip the confirmation before posting")
    p.add_argument("--key", default=None, help="set: any option name (config options lists them)")
    p.add_argument("--value", default=None, help="set: value for --key (lists are comma-separated)")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("start", help="Create or resume a mockup session and run its local server")
    p.add_argument("--title", required=True, help="Screen or topic name; the same title resumes the same session")
    p.add_argument("--issue", type=int, default=None, help="Related issue number")
    p.add_argument("--open", action="store_true", help="Open the URL in the default browser")
    p.add_argument("--idle-seconds", type=int, default=None, help="Override the idle timeout for this run")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("status", help="Current session, URL and folders; recovers them after a lost context")
    p.add_argument("--title", default=None, help="This session (default: the last one started in this project)")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("stop", help="Stop this session's server; the mockups are kept")
    p.add_argument("--all", action="store_true", help="Every session of this project")
    p.add_argument("--title", default=None, help="This session (default: the last one started in this project)")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("choices", help="Clicks recorded in the browser")
    p.add_argument("--title", default=None, help="This session (default: the last one started in this project)")
    p.add_argument("--screen", default=None, help="Only this mockup file")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_choices)

    p = sub.add_parser("tokens", help="Find this project's design files; --save keeps them in the project notes")
    p.add_argument("--save", action="store_true", help="Save file hashes and create the notes if missing")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_tokens)

    p = sub.add_parser("check", help="Flag colors outside tokens.css, unloaded fonts, external URLs, broken paths")
    p.add_argument("--title", default=None, help="This session (default: the last one started in this project)")
    p.add_argument("--screen", default=None, help="Only this mockup file")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("capture", help="Mockup > PNG (whole page or per option), or steps > GIF; no viewer toolbar")
    p.add_argument("--title", default=None, help="This session (default: the last one started in this project)")
    p.add_argument("--screen", default=None, help="Mockup file name (default: the newest)")
    p.add_argument("--option", default=None, help="Only the card with this data-choice value")
    p.add_argument("--all-options", action="store_true", help="One PNG per option")
    p.add_argument("--device", default=None, help="phone, tablet or desktop")
    p.add_argument("--theme", default=None, help="light or dark")
    p.add_argument("--speed", type=int, default=None, help="Motion speed multiplier")
    p.add_argument("--gif", action="store_true", help="Run --steps and record them")
    p.add_argument("--steps", default=None, help="Steps JSON file (format: references/sharing.md)")
    p.add_argument("--max-frames", type=int, default=120)
    p.add_argument("--max-width", type=int, default=900)
    p.add_argument("--out", default=None, help="Output folder (default: {run_dir}/captures)")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("decide", help="Record the chosen option and why, for the skills that come next")
    p.add_argument("--title", default=None, help="This session (default: the last one started in this project)")
    p.add_argument("--choice", required=True, help="The chosen option's id")
    p.add_argument("--reason", required=True, help="Why, in one line")
    p.add_argument("--screen", default=None, help="Mockup file (default: where it was clicked, or the newest)")
    p.add_argument("--issue", type=int, default=None, help="Related issue number")
    p.add_argument("--comment-url", default=None, help="Issue comment that shows it, if posted")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_decide)

    p = sub.add_parser("decision", help="Read the latest recorded decision (empty is fine)")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_decision)

    p = sub.add_parser("get-output-path", help="Output location for this request")
    p.add_argument("--root", default=None)
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
                     "next": "ui_design_cli.py <subcommand> --help"})
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
