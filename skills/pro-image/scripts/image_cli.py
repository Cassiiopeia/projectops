#!/usr/bin/env python3
"""image_cli: pro-image 실행·사실 수집 CLI — 프롬프트 작성과 판단은 에이전트, 출력은 항상 JSON (ok·code·summary·next)
이미지 도구는 우선순위 순(기본 codex > antigravity > claude-vector), 표준 라이브러리 전용 (Pillow 는 있으면 사용)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pro_image import background, commands, history  # noqa: E402


class _BadArgumentsExit(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class JsonArgumentParser(argparse.ArgumentParser):
    """인자 오류를 stderr 대신 JSON 으로 돌려주기 위한 파서"""

    def error(self, message):
        raise _BadArgumentsExit(message)


def emit(payload: dict) -> int:
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()
    return 0 if payload["ok"] else 1


def _with_harness(sub):
    sub.add_argument("--harness", help="harness folder (default: image.harness_dir or docs/image-harness)")
    return sub


def _add_generation_commands(commands_parser) -> None:
    run = _with_harness(commands_parser.add_parser("run"))
    run.add_argument("--name", required=True, help="output file stem, e.g. bg_cafe_night")
    run.add_argument("--prompt", required=True, help="prompt file the agent wrote")
    run.add_argument("--size", required=True, help="final size, e.g. 1536x1024")
    run.add_argument("--alpha", action="store_true", help="transparent background required")
    run.add_argument("--ref", nargs="+", help="reference images to attach")
    run.add_argument("--provider", help="tool to use (default: first ready one in image.priority)")
    run.add_argument("--key-color", help="background key for tools without transparency (default #00FF00)")
    run.add_argument("--kind", help="kind guide used (kept in history)")
    run.set_defaults(handler=commands.cmd_run)
    check = commands_parser.add_parser("check")
    check.add_argument("path")
    check.add_argument("--size")
    check.add_argument("--alpha", action="store_true")
    check.set_defaults(handler=commands.cmd_check)
    remove = commands_parser.add_parser("remove-bg")
    remove.add_argument("path")
    remove.add_argument("--out", required=True)
    remove.add_argument("--key-color", help="exact background color, e.g. #00FF00 (default: detect from the border)")
    remove.add_argument("--tolerance", type=float, default=background.DEFAULT_TOLERANCE)
    remove.add_argument("--mode", choices=("flood", "global"), help="flood: only border-connected; global: every match")
    remove.set_defaults(handler=commands.cmd_remove_bg)
    fit = commands_parser.add_parser("fit")
    fit.add_argument("path")
    fit.add_argument("--out", required=True)
    fit.add_argument("--size", required=True)
    fit.add_argument("--mode", choices=("cover", "contain"), default="cover")
    fit.set_defaults(handler=commands.cmd_fit)
    render = commands_parser.add_parser("render-svg")
    render.add_argument("svg")
    render.add_argument("--out", required=True)
    render.add_argument("--size", required=True)
    render.set_defaults(handler=commands.cmd_render_svg)
    board = commands_parser.add_parser("board")
    board.add_argument("images", nargs="+", help="candidate images in the order to number them")
    board.add_argument("--out", required=True)
    board.set_defaults(handler=commands.cmd_board)


def _add_harness_commands(commands_parser) -> None:
    harness_parser = _with_harness(commands_parser.add_parser("harness"))
    harness_parser.add_argument("--init", action="store_true", help="create the skeleton (never overwrites)")
    harness_parser.add_argument("--character", nargs="+", help="character ids to create with --init")
    harness_parser.set_defaults(handler=commands.cmd_harness)
    kind = _with_harness(commands_parser.add_parser("kind"))
    kind.add_argument("kind")
    kind.set_defaults(handler=commands.cmd_kind)
    record = _with_harness(commands_parser.add_parser("record"))
    record.add_argument("--name", required=True)
    record.add_argument("--status", required=True, choices=history.STATUSES)
    record.add_argument("--kind")
    record.add_argument("--provider")
    record.add_argument("--image")
    record.add_argument("--placed-at", help="where it went in the app")
    record.add_argument("--note", help="why approved or rejected")
    record.set_defaults(handler=commands.cmd_record)
    listing = _with_harness(commands_parser.add_parser("history"))
    listing.add_argument("--kind")
    listing.add_argument("--status", choices=history.STATUSES)
    listing.add_argument("--limit", type=int, default=10)
    listing.set_defaults(handler=commands.cmd_history)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="image_cli.py", description="pro-image: generate image assets with AI tools")
    commands_parser = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)
    commands_parser.add_parser("providers").set_defaults(handler=commands.cmd_providers)
    _add_harness_commands(commands_parser)
    _add_generation_commands(commands_parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except _BadArgumentsExit as error:
        return emit({"ok": False, "code": "bad_args", "summary": error.message, "next": "--help"})
    try:
        return emit(args.handler(args))
    except KeyboardInterrupt:
        return emit({"ok": False, "code": "interrupted", "summary": "Stopped by the user"})
    except (RuntimeError, OSError, ValueError) as error:
        # 변환 도구 없음·읽을 수 없는 이미지·지원 안 하는 PNG 형식 (UnsupportedPng 는 ValueError)
        return emit({"ok": False, "code": "image_tool_failed", "summary": str(error)[-400:],
                     "next": "install Pillow (pip install pillow) for JPEG/WebP input, or pass a PNG"})


if __name__ == "__main__":
    sys.exit(main())
