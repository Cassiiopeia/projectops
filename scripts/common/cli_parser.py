# scripts/common/cli_parser.py
"""JSON-friendly argparse wrapper.

argparse 기본 동작은 인자 오류 시 stderr text + SystemExit(2)를 던진다.
agent는 stdout JSON만 파싱하므로, 이 출력을 self-correct에 활용할 수 없다.

`JSONArgumentParser`는 `error()`/`exit()`를 override하여 실패도
`emit({"ok": False, "code": "bad_args", ...})`로 stdout JSON에 출력한다.

`--help`는 그대로 SystemExit(0)으로 둬서 사람이 직접 실행할 때 도움말이 보인다.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from common.emit import emit


class _BadArgsExit(SystemExit):
    """run_cli가 잡아서 JSON으로 변환하는 sentinel."""
    def __init__(self, message: str, parser: "JSONArgumentParser"):
        super().__init__(2)
        self.message = message
        self.parser = parser


class JSONArgumentParser(argparse.ArgumentParser):
    """argparse 실패를 JSON으로 변환하기 위한 sentinel 예외만 던진다."""

    def error(self, message: str) -> None:
        raise _BadArgsExit(message, self)

    def exit(self, status: int = 0, message: Optional[str] = None) -> None:
        if status == 0:
            super().exit(status, message)
            return
        raise _BadArgsExit(message or "exit", self)


def positive_int(value: str) -> int:
    """1 이상의 정수만 받는 argparse type. `--limit -1`·`0` 이 조용히 빈 결과를 내지 않게 한다 (#713)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"정수가 필요합니다: {value!r}")
    if n < 1:
        raise argparse.ArgumentTypeError(f"1 이상이어야 합니다: {n}")
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
        return f"{parser.prog} <subcommand> — available: {', '.join(subs)}. 사용법은 `{parser.prog} <subcommand> --help`로 확인."
    return f"{parser.prog} --help"


def run_cli(parser: JSONArgumentParser, argv: Optional[Sequence[str]] = None) -> int:
    """argparse 실행 + JSON 변환 래퍼.

    성공: parsed.func(args) 반환값 (보통 0/1)
    실패: stdout에 JSON emit 후 1 반환.
    --help: argparse 기본 동작 그대로 (SystemExit 0).
    """
    try:
        args = parser.parse_args(argv)
    except _BadArgsExit as e:
        return emit({
            "ok": False,
            "code": "bad_args",
            "error": e.message,
            "hint": _make_hint(e.parser),
            "available_subcommands": _list_subcommands(e.parser),
        })
    if not hasattr(args, "func"):
        return emit({
            "ok": False,
            "code": "bad_args",
            "error": "서브커맨드가 지정되지 않았습니다.",
            "hint": _make_hint(parser),
            "available_subcommands": _list_subcommands(parser),
        })
    try:
        return args.func(args)
    except Exception as e:
        return emit({
            "ok": False,
            "code": "handler_error",
            "error": f"{type(e).__name__}: {e}",
        })
