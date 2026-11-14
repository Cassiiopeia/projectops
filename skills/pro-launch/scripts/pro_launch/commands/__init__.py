"""Subcommands — one module is one subcommand (or one group).

New subcommand: put a module in this folder and export `COMMANDS = [Command(name=..., help=..., run=..., configure=...)]`.
`registry.discover_commands` builds the parser, help and dispatch, so no other file needs editing.

Rule: commands do not import each other. Anything two or more share goes down into `runtime/` (checked by tests/test_launch_architecture.py).
"""
