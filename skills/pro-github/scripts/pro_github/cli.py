"""파서 조립: commands/ 모듈의 COMMANDS 를 HELP_ORDER 순서로 등록."""
from __future__ import annotations

import functools

from common.cli_parser import JSONArgumentParser
from pro_github.commands import (
    actions, actions_secrets, api_call, assignees, comments, conventions, finish, images, issues, labels, pulls,
    repository,
)
from pro_github.registry import Command

# 도움말·invalid choice 목록에 보이는 순서. 여기 없는 명령은 이름순으로 뒤에 붙는다
HELP_ORDER = (
    "get-issue", "get-issues", "create-issue", "list-issues", "update-issue", "close-issue", "reopen-issue", "finish-issue",
    "add-comment", "list-comments", "edit-comment", "delete-comment",
    "list-labels", "add-labels", "remove-label", "set-labels", "add-assignees", "remove-assignees",
    "create-pr", "list-prs", "update-pr", "get-pr", "add-pr-comment", "close-pr", "reopen-pr", "merge-pr",
    "search-issues", "get-output-path", "normalize-title", "create-branch-name", "get-commit-template",
    "explore", "upload-image", "delete-image", "secrets", "actions", "api",
)

_MODULES = (issues, finish, comments, labels, assignees, pulls, conventions, repository, images,
            actions_secrets, actions, api_call)


def load_commands() -> list[Command]:
    """모듈 선언 수집 > 이름 중복 검사 > HELP_ORDER 정렬"""
    found: dict[str, Command] = {}
    for module in _MODULES:
        for command in module.COMMANDS:
            if command.name in found:
                raise ValueError(f"duplicate subcommand name: {command.name}")
            found[command.name] = command
    first = [found[name] for name in HELP_ORDER if name in found]
    rest = [found[name] for name in sorted(found) if name not in HELP_ORDER]
    return first + rest


def build_parser(api) -> JSONArgumentParser:
    """api: 핸들러가 GitHub 호출·PAT 조회에 쓰는 의존 창구 (registry.Dependencies)"""
    parser = JSONArgumentParser(
        prog="github_cli",
        description="GitHub API CLI for the pro-github skill",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for command in load_commands():
        command_parser = sub.add_parser(command.name, help=command.help)
        command.configure(command_parser)
        command_parser.set_defaults(func=functools.partial(command.run, api=api))
    return parser
