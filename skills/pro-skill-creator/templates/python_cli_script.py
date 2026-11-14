#!/usr/bin/env python3
"""<scope>_cli — CLI for <skill name> (projectops 3-layer standard skeleton).

This file is the standard skeleton copied when creating a new skill.
3-layer architecture Layer 2 (`skills/<skill>/scripts/<scope>_cli.py`).

Standard (see `skills/references/script-invocation.md`):
- Layer 1 (`scripts/common/`): shared infrastructure (gh_client, config, paths, title etc.)
- Layer 2 (this file): 1 skill = 1 py = argparse subcommands
- Layer 3 (SKILL.md): self-contained 5-line Bash call

Usage:
    1. Copy this file to skills/suh-<new>/scripts/<scope>_cli.py.
    2. Replace the prog name + subcommands for the new skill.
    3. Import shared logic as `from common.<module> import ...` (do not rewrite it).
    4. Use the standard 5-line pattern in SKILL.md code blocks.

Call example (SKILL.md):
    PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
    [ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
    cd "$PROJECT_ROOT/skills/<skill>/scripts" || exit 1
    PYTHONIOENCODING=utf-8 "$PYTHON" <scope>_cli.py <subcommand> [args]

Output: every subcommand prints MCP-style JSON to stdout (4 fields required: ok/code/summary/next).
Write output strings (summary·error·next·argparse help) in English — comments and docstrings too (#769, #1212).
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

# Bootstrap — adjust sys.path so scripts/common can be imported (works regardless of cwd)
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]  # skills/<x>/scripts/<x>_cli.py → 3 up = project root
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402

# Shared logic imports for a new skill:
# from common.gh_client import GitHubAPIError, get_issue  # noqa: E402
# from common.config import get_github_pat  # noqa: E402


# =========================================================================
# Subcommand handlers
# =========================================================================

def cmd_example(args) -> int:
    """Example subcommand — echoes the argument back.

    In a real skill, replace this function with domain logic:
        - import common.gh_client to call the GitHub API
        - auto-load the PAT with common.config get_github_pat()
        - return the result dict via emit() (4 fields guaranteed)
    """
    return emit({
        "input": args.text,
        "summary": f"Input: {args.text}",
        # Add a next hint if needed:
        # "next": f"another-cmd {args.text}",
    })


# =========================================================================
# argparse setup
# =========================================================================

def build_parser() -> argparse.ArgumentParser:
    """argparse subparser definitions. Register new subcommands here."""
    parser = argparse.ArgumentParser(
        prog="<scope>_cli",
        description="<skill name> skill CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ex = sub.add_parser("example", help="Example subcommand")
    p_ex.add_argument("text")
    p_ex.set_defaults(func=cmd_example)

    # Pattern for adding a new subcommand:
    # p_new = sub.add_parser("new-cmd", help="What the subcommand does")
    # p_new.add_argument("owner")
    # p_new.add_argument("repo")
    # p_new.add_argument("--state", choices=["open", "closed"], default="open")
    # p_new.set_defaults(func=cmd_new)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
