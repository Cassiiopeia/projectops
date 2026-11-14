# scripts/common/cli_parser.py
"""JSON-friendly argparse wrapper.

By default argparse writes stderr text and raises SystemExit(2) on bad arguments.
The agent parses only stdout JSON, so it cannot use that output to self-correct.

`JSONArgumentParser` overrides `error()`/`exit()` so failures are also
printed to stdout as JSON via `emit({"ok": False, "code": "bad_args", ...})`.

`--help` still raises SystemExit(0), so a human running it directly sees the help.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

import difflib
import re

from common.emit import configure_output, emit


class _BadArgsExit(SystemExit):
    """Sentinel that run_cli catches and turns into JSON."""
    def __init__(self, message: str, parser: "JSONArgumentParser"):
        super().__init__(2)
        self.message = message
        self.parser = parser


class JSONArgumentParser(argparse.ArgumentParser):
    """Only raises the sentinel exception so argparse failures can become JSON."""

    def error(self, message: str) -> None:
        raise _BadArgsExit(message, self)

    def exit(self, status: int = 0, message: Optional[str] = None) -> None:
        if status == 0:
            super().exit(status, message)
            return
        raise _BadArgsExit(message or "exit", self)


def positive_int(value: str) -> int:
    """argparse type accepting integers >= 1. Keeps `--limit -1`/`0` from silently returning nothing (#713)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"an integer is required: {value!r}")
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or greater: {n}")
    return n


def _list_subcommands(parser: argparse.ArgumentParser) -> list:
    subs = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subs.extend(sorted(action.choices.keys()))
    return subs


def _make_hint(parser: argparse.ArgumentParser) -> str:
    subs = _list_subcommands(parser)
    if subs:
        return f"{parser.prog} <subcommand> — available: {', '.join(subs)}. See `{parser.prog} <subcommand> --help` for usage."
    return f"{parser.prog} --help"


# Global output options taking one value: --field a.b / --fields a,b (CLIs spell it differently, so accept both)
_FIELD_OPTIONS = ("--field", "--fields")


def _extract_output_options(argv: list) -> tuple:
    """Pull global output options (--brief, --field(s) X) from argv. (remaining argv, brief, field, should_return_object)
    should_return_object: given via --fields, return {path: value} JSON even for one path (#1187)"""
    rest, brief, field, should_return_object, skip_next = [], False, None, False, False
    for position, token in enumerate(argv):
        option_name = token.split("=", 1)[0]
        if skip_next:
            skip_next = False
        elif token == "--brief":
            brief = True
        elif token in _FIELD_OPTIONS and position + 1 < len(argv):
            field, skip_next = argv[position + 1], True
            should_return_object = token == "--fields"
        elif option_name in _FIELD_OPTIONS and "=" in token:
            field = token.split("=", 1)[1]
            should_return_object = option_name == "--fields"
        else:
            rest.append(token)
    return rest, brief, field, should_return_object


def _did_you_mean(message: str, parser: argparse.ArgumentParser) -> list:
    """For an invalid choice error, the closest subcommand candidates"""
    found = re.search(r"invalid choice: '([^']*)'", message)
    return difflib.get_close_matches(found.group(1), _list_subcommands(parser), n=3, cutoff=0.5) if found else []


def run_cli(parser: JSONArgumentParser, argv: Optional[Sequence[str]] = None) -> int:
    """Run argparse and convert to JSON.

    Success: return value of parsed.func(args) (usually 0/1)
    Failure: emit JSON to stdout and return 1.
    --help: default argparse behaviour (SystemExit 0).
    """
    argv, brief, field, should_return_object = _extract_output_options(list(sys.argv[1:] if argv is None else argv))
    from common.stable_entry import refresh_and_check
    configure_output(brief=brief, field=field, should_return_object=should_return_object, extra={"newer_installed": info} if (info := refresh_and_check(sys.argv[0])) else None)
    try:
        args = parser.parse_args(argv)
    except _BadArgsExit as e:
        # Put usage inside the response: the agent reads only stdout JSON and had to call --help separately
        return emit({
            "ok": False,
            "code": "bad_args",
            "error": e.message,
            "usage": e.parser.format_usage().strip(),
            "did_you_mean": _did_you_mean(e.message, e.parser),
            "hint": _make_hint(e.parser),
            "available_subcommands": _list_subcommands(e.parser),
            "next": f"check the arguments with `{e.parser.prog} --help`, fix them and run again",
        })
    if not hasattr(args, "func"):
        return emit({
            "ok": False,
            "code": "bad_args",
            "error": "no subcommand given.",
            "hint": _make_hint(parser),
            "available_subcommands": _list_subcommands(parser),
            "next": f"list the subcommands with `{parser.prog} --help`",
        })
    try:
        return args.func(args)
    except Exception as e:
        return emit({
            "ok": False,
            "code": "handler_error",
            "error": f"{type(e).__name__}: {e}",
            "next": "check the inputs (paths, values) and run again",
        })
