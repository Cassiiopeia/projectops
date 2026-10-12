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

    def __post_init__(self) -> None:
        if self.needs not in NEEDS:
            raise ValueError(f"needs 는 {NEEDS} 중 하나여야 한다: {self.needs!r}")


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
                raise ValueError(f"서브커맨드 이름이 겹친다: {cmd.name} ({mod_name})")
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
            raise ValueError(f"동작 이름이 겹친다: {act.name} ({mod_name})")
        found[act.name] = act
    return dict(sorted(found.items()))
