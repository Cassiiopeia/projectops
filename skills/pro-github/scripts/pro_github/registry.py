"""Subcommand declarations (Command) and the dependency lookup gateway (Dependencies)."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Command:
    """One subcommand: name, help, run function run(args, api), argument setup configure(parser)."""

    name: str
    help: str
    run: Callable[[argparse.Namespace, Any], int]
    configure: Callable[[argparse.ArgumentParser], None]


class Dependencies:
    """Gateway that reads the entry module's globals (gh_client functions, get_github_pat) at call time.

    When tests swap github_cli module attributes, handlers see the change too (values are not copied)
    """

    def __init__(self, namespace: dict[str, Any]) -> None:
        self._namespace = namespace

    def __getattr__(self, name: str) -> Any:
        try:
            return self._namespace[name]
        except KeyError:
            raise AttributeError(name) from None
