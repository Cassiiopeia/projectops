#!/usr/bin/env python3
"""image_cli: pro-image run and fact-gathering CLI — the agent writes prompts and decides; output is always JSON (ok, code, summary, next)
Image tools in priority order (default codex > antigravity > claude-vector), stdlib only (uses Pillow if present)
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
    """Parser that returns argument errors as JSON instead of stderr"""

    def error(self, message):
        raise _BadArgumentsExit(message)


# Global output options (same contract as scripts/common/emit.py, #1181) — this CLI does not use common, so a small copy
# Guidance keys kept by --brief / identity keys of list rows
_BRIEF_GUIDE_KEYS = ("ok", "code", "summary", "next", "error", "hint", "usage", "example", "count", "warning", "warnings")
_BRIEF_ROW_KEYS = ("number", "id", "run_id", "job_id", "title", "name", "state", "status", "conclusion")
# --field a.b: raw value / --fields a,b: always {path: value} JSON
_FIELD_OPTIONS = ("--field", "--fields")
_output_options: dict = {"brief": False, "field": None, "should_return_object": False}


def _extract_output_options(argv: list[str]) -> list[str]:
    """Pull --brief and --field(s) out of argv into _output_options, return the rest of argv"""
    rest, skip_next = [], False
    for position, token in enumerate(argv):
        option_name, has_inline_value, inline_value = token.partition("=")
        if skip_next:
            skip_next = False
        elif token == "--brief":
            _output_options["brief"] = True
        elif option_name in _FIELD_OPTIONS and (has_inline_value or position + 1 < len(argv)):
            _output_options["field"] = inline_value if has_inline_value else argv[position + 1]
            _output_options["should_return_object"] = option_name == "--fields"
            skip_next = not has_inline_value
        else:
            rest.append(token)
    return rest


def _lookup(payload, dotted_path: str):
    """a.b.0 path > value (KeyError, IndexError, ValueError if missing)"""
    current = payload
    for part in dotted_path.split("."):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def _shape_output(payload: dict):
    """Apply --field(s) to success responses, --brief otherwise (error responses are not filtered by --field)"""
    field = _output_options["field"]
    if field and payload["ok"]:
        paths = [path.strip() for path in field.split(",") if path.strip()]
        values = {}
        for path in paths:
            try:
                values[path] = _lookup(payload, path)
            except (KeyError, IndexError, ValueError, TypeError):
                return {"ok": False, "code": "field_not_found", "summary": f"the response has no '{path}'",
                        "next": "call again with a key from available_keys", "available_keys": list(payload)}
        return values if _output_options["should_return_object"] or len(paths) > 1 else values[paths[0]]
    if not _output_options["brief"]:
        return payload
    brief = {}
    for key, value in payload.items():
        if key in _BRIEF_GUIDE_KEYS:
            brief[key] = value
        elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            brief[key] = [{row_key: item[row_key] for row_key in _BRIEF_ROW_KEYS if row_key in item} for item in value]
    return brief


def emit(payload: dict) -> int:
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    shaped = _shape_output(payload)
    # String --field values print verbatim (same as common)
    if isinstance(shaped, str):
        sys.stdout.write(shaped + "\n")
        sys.stdout.flush()
        return 0
    # Non-UTF-8 console (Windows cp949, cp1252): non-ASCII paths as \uXXXX (? replacement breaks paths; JSON restores them)
    is_utf8_stdout = (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "") == "utf8"
    sys.stdout.write(json.dumps(shaped, ensure_ascii=not is_utf8_stdout, default=str) + "\n")
    sys.stdout.flush()
    is_field_missing = isinstance(shaped, dict) and shaped.get("code") == "field_not_found"
    return 0 if payload["ok"] and not is_field_missing else 1


def _with_harness(sub):
    sub.add_argument("--harness", help="harness folder (default: image.harness_dir or docs/image-harness)")
    return sub


def _add_generation_commands(commands_parser) -> None:
    run = _with_harness(commands_parser.add_parser("run"))
    run.add_argument("--name", required=True, help="output file stem, e.g. bg_cafe_night")
    run.add_argument("--prompt", required=True, help="prompt file the agent wrote")
    run.add_argument("--size", required=True, help="final size, e.g. 1536x1024")
    run.add_argument("--alpha", action="store_true", help="transparent background required")
    # extend: repeated --ref accumulates instead of overwriting the earlier list (#1183)
    run.add_argument("--ref", nargs="+", action="extend", help="reference images to attach (repeatable)")
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
    harness_parser.add_argument("--character", nargs="+", action="extend",
                                help="character ids to create with --init (repeatable)")
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
        args = build_parser().parse_args(_extract_output_options(list(sys.argv[1:] if argv is None else argv)))
    except _BadArgumentsExit as error:
        return emit({"ok": False, "code": "bad_args", "summary": error.message, "next": "--help"})
    try:
        return emit(args.handler(args))
    except KeyboardInterrupt:
        return emit({"ok": False, "code": "interrupted", "summary": "Stopped by the user"})
    except (RuntimeError, OSError, ValueError) as error:
        # No converter, unreadable image, unsupported PNG format (UnsupportedPng is a ValueError)
        return emit({"ok": False, "code": "image_tool_failed", "summary": str(error)[-400:],
                     "next": "install Pillow (pip install pillow) for JPEG/WebP input, or pass a PNG"})


if __name__ == "__main__":
    sys.exit(main())
