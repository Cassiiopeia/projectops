"""파서 조립과 `main()` — 명령 선언을 모아 CLI 하나로 만든다.

여기에는 명령별 지식이 없다. 무엇이 있는지는 `commands/` 가 선언하고, 이 파일은 모아서 돌릴 뿐이다.
출력은 언제나 JSON 하나다 — 인자 오류도, 예상 못 한 예외도 트레이스백이 아니라 JSON 으로 끝낸다.
"""
from __future__ import annotations

import argparse
import sys

from common.emit import emit

from pro_launch import registry
from pro_launch.registry import Command
from pro_launch.runtime.context import ACCESS_CTX, ROOT_CTX

# 도움말에서 보이는 순서. 여기 없는 명령은 이름순으로 뒤에 붙는다 (등록 자체는 이 표와 무관하다)
HELP_ORDER = ("doctor", "detect", "devices", "device", "app", "web", "render", "http", "access", "db",
              "logs", "cred", "local", "ssh", "shrink", "recall", "learn", "tidy", "forget",
              "get-output-path")


def load_commands() -> list[Command]:
    """commands/ 아래 선언을 모아 도움말 순서대로 돌려준다."""
    from pro_launch import commands

    found = {c.name: c for c in registry.discover_commands(commands)}
    first = [found[n] for n in HELP_ORDER if n in found]
    rest = [found[n] for n in sorted(found) if n not in HELP_ORDER]
    return first + rest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="launch_cli",
                                     description="앱·웹·서버를 띄우고 조작하고 찍는다")
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in load_commands():
        p = sub.add_parser(cmd.name, help=cmd.help)
        if cmd.configure:
            cmd.configure(p)
        p.set_defaults(func=cmd.run, _tail_dest=cmd.tail_dest)
    return parser


def _split_tail(raw: list[str], commands: list[Command]) -> tuple[list[str], list[str]]:
    """`--` 를 쓰는 명령(local sudo -- <명령>)은 그 뒤를 파서에 넘기지 않는다.

    argparse 의 REMAINDER 는 앞의 --cred 같은 옵션까지 삼키므로 미리 잘라 두었다가
    `args.<tail_dest>` 로 되돌려 준다 (#784).
    """
    if raw and "--" in raw:
        owner = next((c for c in commands if c.name == raw[0]), None)
        if owner and owner.tail_dest:
            i = raw.index("--")
            return raw[:i], raw[i + 1:]
    return raw, []


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    raw, tail = _split_tail(raw, load_commands())
    try:
        args = parser.parse_args(raw)
        if getattr(args, "_tail_dest", None):
            setattr(args, args._tail_dest, tail)
    except SystemExit as e:
        if e.code in (0, None):
            raise
        payload = {"ok": False, "code": "bad_args",
                   "error": "인자가 올바르지 않습니다 (위 사용법 참고)",
                   "next": "launch_cli.py <서브커맨드> --help"}
        if registry.LOAD_ERRORS:
            # 모듈이 깨져서 서브커맨드가 안 보이는 것일 수 있다 — 원인을 알려 준다
            payload["load_errors"] = dict(registry.LOAD_ERRORS)
        return emit(payload)
    # 한 프로세스에서 main 을 여러 번 부르는 경우(테스트) 이전 호출의 표시가 새지 않게 한다
    ROOT_CTX.clear()
    ACCESS_CTX.clear()
    try:
        return args.func(args)
    except Exception as e:   # 예상 못 한 입력이 트레이스백으로 끝나지 않게 — 에이전트는 JSON 만 읽는다 (#705)
        return emit({"ok": False, "code": "handler_error",
                     "error": f"{type(e).__name__}: {e}",
                     "next": "입력(경로·값)을 확인하고 다시 부른다"})
