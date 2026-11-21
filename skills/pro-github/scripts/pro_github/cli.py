"""Parser assembly: register COMMANDS from commands/ modules in HELP_ORDER."""
from __future__ import annotations

import functools

from common.cli_parser import JSONArgumentParser
from pro_github.commands import (
    actions, actions_secrets, api_call, assignees, comments, conventions, finish, images, issues, labels, pulls,
    repository, repository_admin,
)
from pro_github.registry import Command

# Order shown in help and the invalid choice list. Commands not listed here follow by name
HELP_ORDER = (
    "get-issue", "get-issues", "create-issue", "list-issues", "update-issue", "close-issue", "reopen-issue", "finish-issue",
    "add-comment", "list-comments", "edit-comment", "delete-comment",
    "list-labels", "add-labels", "remove-label", "set-labels", "add-assignees", "remove-assignees",
    "create-pr", "list-prs", "update-pr", "get-pr", "add-pr-comment", "close-pr", "reopen-pr", "merge-pr",
    "search-issues", "get-output-path", "normalize-title", "create-branch-name", "get-commit-template",
    "explore", "create-repo", "update-repo", "delete-repo", "upload-image", "delete-image", "secrets", "actions", "api",
)

_MODULES = (issues, finish, comments, labels, assignees, pulls, conventions, repository, repository_admin, images,
            actions_secrets, actions, api_call)


def load_commands() -> list[Command]:
    """Collect module declarations > check for duplicate names > sort by HELP_ORDER"""
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
    """api: dependency gateway handlers use for GitHub calls and PAT lookup (registry.Dependencies)"""
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
