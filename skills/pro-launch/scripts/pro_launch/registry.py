"""명령과 동작의 선언 · 자동 발견.

새 서브커맨드는 `commands/` 에 모듈 하나를 두고 `COMMANDS` 를 내보내면 끝이다.
새 `web`·`app` 동작은 그 명령의 `actions/` 에 모듈 하나를 두고 `ACTION` 을 내보내면 끝이다.
다른 파일은 고치지 않는다 — 파서 · 도움말 · 디스패치가 이 선언에서 만들어진다.

모듈 하나가 import 에서 실패해도 다른 명령은 돌아야 한다. 실패는 `LOAD_ERRORS` 에 담아 두었다가
그 명령을 불렀을 때만 알린다.
"""
from __future__ import annotations

import argparse
import importlib
import pkgutil
from dataclasses import dataclass
from typing import Callable

# 동작이 무엇을 필요로 하는지. 디스패처가 이 값으로 준비를 정한다.
#   nothing        run(args)                      — 상태도 브라우저도 안 읽는다 (web setup)
#   launch         run(args, root, state_file)    — 브라우저를 새로 띄운다 (web open)
#   state_offline  run(args, state, state_file)   — 상태 파일만 만진다. 브라우저가 없어도 된다
#   state_online   run(args, state, state_file)   — 떠 있는 브라우저의 정보가 있어야 하나 연결은 맺지 않는다
#   page           run(page, args, state) -> dict — 붙어서 한 페이지를 조작한다. 결과 dict 를 돌려준다
NEEDS = ("nothing", "launch", "state_offline", "state_online", "page")
# 동작이 기기를 어떻게 쓰는지 (#953). 디스패처가 이 값으로 소유 확인·기록을 한다
#   mutate  기기·앱 상태를 바꾼다 — 다른 세션 소유면 --yes 없이 거부
#   read    읽기만 한다 — 다른 세션 소유면 경고만
#   none    기기를 쓰지 않거나 동작이 직접 판정한다
DEVICE_USES = ("mutate", "read", "none")


@dataclass(frozen=True)
class Command:
    """서브커맨드 하나. `name` 이 CLI 에서 부르는 이름이다."""

    name: str
    help: str
    run: Callable[[argparse.Namespace], int]
    configure: Callable[[argparse.ArgumentParser], None] | None = None
    # `--` 뒤를 파서에 넘기지 않고 이 이름의 인자로 되돌려 준다 (예: local sudo -- <명령>)
    tail_dest: str | None = None


@dataclass(frozen=True)
class Action:
    """`web`·`app` 같은 명령 안의 동작 하나. 자기만의 옵션은 `configure` 로 붙인다."""

    name: str
    run: Callable
    needs: str = "page"
    configure: Callable[[argparse.ArgumentParser], None] | None = None
    # `<명령> <동작> --help` 의 한 줄 설명 · 예시 한 줄
    help: str = ""
    example: str = ""
    # 이 동작이 쓰는 공통 옵션 이름. None 이면 공통 옵션을 전부 받는다 (동작별로 나누지 않은 명령 — app)
    options: tuple[str, ...] | None = None
    # 기기를 쓰는 명령(app)의 동작은 반드시 선언한다 (DEVICE_USES) — 테스트가 빠진 것을 잡는다
    device_use: str | None = None

    def __post_init__(self) -> None:
        if self.needs not in NEEDS:
            raise ValueError(f"needs must be one of {NEEDS}: {self.needs!r}")
        if self.device_use is not None and self.device_use not in DEVICE_USES:
            raise ValueError(f"device_use must be one of {DEVICE_USES}: {self.device_use!r}")
        if self.options is not None and not isinstance(self.options, tuple):
            raise ValueError(f"options must be a tuple: {self.options!r}")


# 모듈 이름 → 오류. 한 모듈이 깨져도 나머지 명령은 돈다
LOAD_ERRORS: dict[str, str] = {}


def _modules(package):
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        full = f"{package.__name__}.{info.name}"
        try:
            yield info.name, importlib.import_module(full)
        except Exception as e:   # noqa: BLE001 — 모듈 하나가 전체를 막으면 안 된다
            LOAD_ERRORS[info.name] = f"{type(e).__name__}: {e}"


def discover_commands(package) -> list[Command]:
    """`package` 아래 모듈이 내보낸 `COMMANDS` 를 모은다. 이름이 겹치면 오류다."""
    found: dict[str, Command] = {}
    for mod_name, mod in _modules(package):
        for cmd in getattr(mod, "COMMANDS", []):
            if cmd.name in found:
                raise ValueError(f"Duplicate subcommand name: {cmd.name} ({mod_name})")
            found[cmd.name] = cmd
    return list(found.values())


def discover_actions(package) -> dict[str, Action]:
    """`package`(actions 폴더) 아래 모듈이 내보낸 `ACTION` 을 이름순으로 모은다."""
    found: dict[str, Action] = {}
    for mod_name, mod in _modules(package):
        act = getattr(mod, "ACTION", None)
        if act is None:
            continue
        if act.name in found:
            raise ValueError(f"Duplicate action name: {act.name} ({mod_name})")
        found[act.name] = act
    return dict(sorted(found.items()))


# ── 동작별 파서 (#896) ────────────────────────────────────────────────────
#
# 공통 옵션을 한 파서에 다 달면 `web type --help` 에 30개가 나오고, 그 동작이 안 쓰는 옵션도 조용히 받아 버린다.
# 동작마다 하위 파서를 두고 그 동작이 쓴다고 선언한 공통 옵션 + 자기 옵션만 단다.


class ActionParser(argparse.ArgumentParser):
    """동작 하나의 파서. 그 동작이 받지 않는 옵션은 조용히 넘기지 않고 쓸 수 있는 옵션과 함께 거절한다."""

    def parse_known_args(self, args=None, namespace=None):
        namespace, extras = super().parse_known_args(args, namespace)
        unsupported = [a.split("=", 1)[0] for a in extras if a.startswith("-") and len(a) > 1]
        if unsupported:
            # cli.main 이 stderr 마지막 줄을 bad_args 의 error 에 싣는다 — 한 줄로 쓴다
            # 앞에 prog(예: launch_cli web type)가 붙으므로 동작 이름은 다시 쓰지 않는다
            self.error(f"This action does not take {' '.join(unsupported)} (unsupported option). "
                       f"Available options: {' '.join(self.option_names())}")
        return namespace, extras

    def option_names(self) -> list[str]:
        """이 파서가 받는 긴 옵션 이름 (--help 제외)."""
        names = []
        for act in self._actions:
            longs = [o for o in act.option_strings if o.startswith("--") and o != "--help"]
            names += longs[:1]
        return names


def shared_option_defaults(shared: dict[str, Callable[[argparse.ArgumentParser], None]]) -> dict:
    """공통 옵션 전부의 (dest → 기본값). 선언하지 않은 동작에도 속성은 있어야 디스패처가 getattr 없이 읽는다.

    같은 플래그를 동작마다 다른 기본값으로 두는 옵션(--timeout)이 있어 하나씩 따로 읽고, 겹치면 표의 앞쪽이 이긴다.
    """
    defaults: dict = {}
    for add in shared.values():
        scratch = argparse.ArgumentParser(add_help=False)
        add(scratch)
        for dest, value in vars(scratch.parse_args([])).items():
            defaults.setdefault(dest, value)
    return defaults


def add_action_parsers(parser: argparse.ArgumentParser, actions: dict[str, Action],
                       shared: dict[str, Callable[[argparse.ArgumentParser], None]],
                       always: tuple[str, ...] = ()) -> None:
    """동작마다 하위 파서를 단다: 항상 붙는 공통 옵션 + 선언한 공통 옵션 + 그 동작의 configure.

    선언하지 않은 공통 옵션은 명령줄에서 받지 않고 기본값만 채운다.
    """
    defaults = shared_option_defaults(shared)
    sub = parser.add_subparsers(dest="action", required=True, metavar="<action>",
                                parser_class=ActionParser)
    for name, action in actions.items():
        chosen = tuple(shared) if action.options is None else always + action.options
        unknown = [o for o in chosen if o not in shared]
        if unknown:
            raise ValueError(f"{name}: unknown shared option {unknown} (available: {sorted(shared)})")
        p = sub.add_parser(name, help=action.help or None, description=action.help or None,
                           epilog=f"e.g. {action.example}" if action.example else None,
                           formatter_class=argparse.RawDescriptionHelpFormatter)
        p.set_defaults(**defaults)
        for option in dict.fromkeys(chosen):
            shared[option](p)
        if action.configure:
            action.configure(p)


def action_usage_lines(parser: argparse.ArgumentParser) -> list[str]:
    """`<명령> --help` 에 붙일 동작별 옵션 요약 — 동작마다 한 줄."""
    sub = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
    if sub is None:
        return []
    lines = []
    for name, p in sub.choices.items():
        options = p.option_names() if isinstance(p, ActionParser) else []
        lines.append(f"  {name:<9} {' '.join(options)}")
    return lines
