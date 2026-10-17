"""서브커맨드 선언(Command)과 의존 조회 창구(Dependencies)."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Command:
    """서브커맨드 하나: 이름·도움말·실행 함수 run(args, api)·인자 등록 configure(parser)."""

    name: str
    help: str
    run: Callable[[argparse.Namespace, Any], int]
    configure: Callable[[argparse.ArgumentParser], None]


class Dependencies:
    """진입 모듈 전역(gh_client 함수·get_github_pat)을 호출 시점에 읽는 창구.

    테스트가 github_cli 모듈 속성을 바꿔 끼우면 핸들러에도 그대로 반영 (값을 복사해 두지 않음)
    """

    def __init__(self, namespace: dict[str, Any]) -> None:
        self._namespace = namespace

    def __getattr__(self, name: str) -> Any:
        try:
            return self._namespace[name]
        except KeyError:
            raise AttributeError(name) from None
