"""파서 조립과 `main()` — 명령 선언을 모아 CLI 하나로 만든다.

여기에는 명령별 지식이 없다. 무엇이 있는지는 `commands/` 가 선언하고, 이 파일은 모아서 돌릴 뿐이다.
출력은 언제나 JSON 하나다 — 인자 오류도, 예상 못 한 예외도 트레이스백이 아니라 JSON 으로 끝낸다.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys

from pro_launch import registry
from pro_launch.registry import Command
from pro_launch.runtime.context import ACCESS_CTX, OUTPUT_CTX, ROOT_CTX
from pro_launch.runtime.output import attach_known_fix, emit_shaped

# 도움말에서 보이는 순서. 여기 없는 명령은 이름순으로 뒤에 붙는다 (등록 자체는 이 표와 무관하다)
HELP_ORDER = ("doctor", "detect", "devices", "device", "app", "web", "render", "http", "access", "db",
              "logs", "cred", "local", "ssh", "shrink", "recall", "learn", "tidy", "forget",
              "kb", "get-output-path")


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
    # 출력 모양 옵션 (#898) — 실제로는 _pop_output_options 가 파서 전에 꺼낸다. 여기 둔 것은 도움말용
    parser.add_argument("--brief", action="store_true",
                        help="핵심 키만 낸다: ok·code·summary·next·error·known_fix·memory·learn_hint")
    parser.add_argument("--fields", metavar="a,b,c",
                        help="이 최상위 키만 남긴다 (ok·code·summary·next·known_fix·memory·learn_hint 는 항상)")
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


BRIEF_OPTION = "--brief"
FIELDS_OPTION = "--fields"


def _pop_output_options(raw: list[str]) -> tuple[list[str], bool, list[str] | None, str | None]:
    """--brief · --fields 를 어느 자리에 있든(서브커맨드 앞·뒤) 꺼낸다 > (나머지, is_brief, 키 목록, 오류).

    서브파서마다 옵션을 다는 대신 파서 전에 꺼낸다 — 중첩 동작(web shot 등)까지 손대지 않고 전부 받는다.
    `--` 뒤(local sudo -- <명령>)는 남의 명령 인자라 건드리지 않는다.
    """
    tail_start = raw.index("--") if "--" in raw else len(raw)
    head, rest = raw[:tail_start], raw[tail_start:]
    kept: list[str] = []
    is_brief = False
    field_names: list[str] | None = None
    index = 0
    while index < len(head):
        token = head[index]
        if token == BRIEF_OPTION:
            is_brief = True
        elif token == FIELDS_OPTION or token.startswith(FIELDS_OPTION + "="):
            if token == FIELDS_OPTION:
                index += 1
                if index >= len(head) or head[index].startswith("--"):
                    return raw, is_brief, field_names, "--fields 에 키 이름이 없습니다 (예: --fields path,url)"
                value = head[index]
            else:
                value = token.split("=", 1)[1]
            names = [name.strip() for name in value.split(",") if name.strip()]
            if not names:
                return raw, is_brief, field_names, "--fields 에 키 이름이 없습니다 (예: --fields path,url)"
            field_names = [*(field_names or []), *names]
        else:
            kept.append(token)
        index += 1
    return kept + rest, is_brief, field_names, None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    raw, is_brief, field_names, option_error = _pop_output_options(raw)
    # 한 프로세스에서 main 을 여러 번 부르는 경우(테스트) 이전 호출의 모양이 새지 않게 매번 새로 적는다
    OUTPUT_CTX.clear()
    OUTPUT_CTX.update(is_brief=is_brief, field_names=field_names)
    if option_error:
        return emit_shaped({"ok": False, "code": "bad_args", "error": f"인자가 올바르지 않습니다: {option_error}",
                            "next": "launch_cli.py <서브커맨드> --help"})
    raw, tail = _split_tail(raw, load_commands())
    err = io.StringIO()
    try:
        # argparse 가 stderr 로 쓰는 원인 문구를 error 에 싣는다 (에이전트는 JSON 만 읽는다)
        with contextlib.redirect_stderr(err):
            args = parser.parse_args(raw)
        if getattr(args, "_tail_dest", None):
            setattr(args, args._tail_dest, tail)
    except SystemExit as e:
        if e.code in (0, None):
            raise
        sys.stderr.write(err.getvalue())
        reason = err.getvalue().strip().splitlines()[-1] if err.getvalue().strip() else ""
        payload = {"ok": False, "code": "bad_args",
                   "error": f"인자가 올바르지 않습니다: {reason}",
                   "next": "launch_cli.py <서브커맨드> --help"}
        if registry.LOAD_ERRORS:
            # 모듈이 깨져서 서브커맨드가 안 보이는 것일 수 있다 — 원인을 알려 준다
            payload["load_errors"] = dict(registry.LOAD_ERRORS)
        attach_known_fix(payload)
        return emit_shaped(payload)
    # 한 프로세스에서 main 을 여러 번 부르는 경우(테스트) 이전 호출의 표시가 새지 않게 한다
    ROOT_CTX.clear()
    ACCESS_CTX.clear()
    try:
        return args.func(args)
    except Exception as e:   # 예상 못 한 입력이 트레이스백으로 끝나지 않게 — 에이전트는 JSON 만 읽는다 (#705)
        payload = {"ok": False, "code": "handler_error", "error": f"{type(e).__name__}: {e}",
                   "next": "입력(경로·값)을 확인하고 다시 부른다"}
        attach_known_fix(payload)
        return emit_shaped(payload)
