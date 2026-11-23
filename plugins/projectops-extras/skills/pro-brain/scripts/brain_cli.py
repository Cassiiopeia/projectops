#!/usr/bin/env python3
"""brain_cli: pro-brain fact collection, onboarding and personal GBrain connection; the agent decides and writes the note.
Output is always JSON (ok, code, summary, next). Read-only except `setup --apply --yes` (repo switch + rule block),
`connect --apply --yes` (one source in the user's own GBrain) and `connect --team --apply --yes` (one user-scope MCP
entry with the token from the credential store, optional .mcp.json), all only after the user agreed.
extras installs only its own folder, so standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brain import collect, commands, install_guide, repo_facts  # noqa: E402


class _BadArgumentsExit(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class JsonArgumentParser(argparse.ArgumentParser):
    """Parser that returns argument errors as JSON instead of stderr"""

    def error(self, message):
        raise _BadArgumentsExit(message)


def emit(payload: dict, text_only: bool = False) -> int:
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    # gaps --format text: plain log lines for brain sync scripts
    output = payload["text"] if text_only and payload["ok"] and "text" in payload else json.dumps(payload, ensure_ascii=False, default=str)
    sys.stdout.write(output + "\n")
    sys.stdout.flush()
    return 0 if payload["ok"] else 1


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="brain_cli.py", description="pro-brain fact collection and onboarding")
    sub = parser.add_subparsers(dest="command", parser_class=JsonArgumentParser)

    status = sub.add_parser("status", help="repo switch, capture mode, open onboarding questions, sync target")
    status.add_argument("--repo", help="repository folder (default: current folder)")

    gather = sub.add_parser("collect", help="metadata for one note (an issue or a change set)")
    gather.add_argument("--repo", help="repository folder (default: current folder)")
    gather.add_argument("--issue", type=int, help="issue number (default: from the branch name in issue-end mode)")
    gather.add_argument("--change-set", action="store_true", help="note for a change set, no issue fields")
    gather.add_argument("--commits", help="comma-separated shas of one topic group (change set)")
    gather.add_argument("--base", help="commit before the first commit of the note (explicit range)")
    gather.add_argument("--head", help="last commit of the note (default: HEAD)")
    gather.add_argument("--branch", help="branch name to record (default: current branch)")
    gather.add_argument("--pr-number", type=int)
    gather.add_argument("--pr-url")
    gather.add_argument("--merge-commit", help="merge commit sha (default: found on the default or development branch)")
    gather.add_argument("--deploy-target", help="where it was deployed, comma-separated, e.g. server,play")
    gather.add_argument("--deploy-version", help="released version, e.g. 1.2.3")
    gather.add_argument("--capture-mode", choices=repo_facts.CAPTURE_MODES, help="override, e.g. manual when asked directly")
    gather.add_argument("--title-hint", help="a few words of the note title, used for the suggested file name")

    setup = sub.add_parser("setup", help="onboarding plan (default) or --apply --yes after the user agreed")
    setup.add_argument("--repo", help="repository folder (default: current folder)")
    setup.add_argument("--capture", choices=repo_facts.CAPTURE_MODES)
    setup.add_argument("--claude-md", choices=("add", "decline"), help="rule block: add it, or remember the no")
    setup.add_argument("--target", help="file for the rule block (default: the recommended one)")
    setup.add_argument("--agents-md", action="store_true", help="also write the block to a tracked AGENTS.md")
    setup.add_argument("--brain-mcp", help="legacy: team brain MCP server name only (prefer --team-brain-name)")
    setup.add_argument("--team-brain-name", help="team brain MCP server name to share, e.g. gbrain-myproject (never 'gbrain')")
    setup.add_argument("--team-brain-url", help="team brain MCP URL, e.g. https://brain.example.com/mcp (no token)")
    setup.add_argument("--team-brain-contact", help="who issues read-only tokens, e.g. a name or a team channel")
    setup.add_argument("--team-brain-off", action="store_true", help="remove the team brain from the switch")
    setup.add_argument("--no-probe", action="store_true", help="do not probe a new --team-brain-url (offline)")
    setup.add_argument("--enable", action="store_true", help="turn capture on (creates the knowledge block if missing)")
    setup.add_argument("--apply", action="store_true", help="write the changes (needs --yes)")
    setup.add_argument("--yes", action="store_true", help="the user agreed in this conversation")

    link = sub.add_parser("connect", help="add this repo's knowledge folder to your own GBrain as one source (plan by default)")
    link.add_argument("--repo", help="repository folder (default: current folder)")
    link.add_argument("--source-id", help="source id (default: <project>-knowledge)")
    link.add_argument("--source-root", help="checkout to read from, e.g. a dedicated clone of the default branch")
    link.add_argument("--no-sync", action="store_true", help="add the source without the first sync")
    link.add_argument("--remote", action="store_true", help="your own brain runs elsewhere (HTTP): print the commands for its host")
    link.add_argument("--team", action="store_true", help="team brain: register the user-scope MCP entry with the stored token")
    link.add_argument("--rotate", action="store_true", help="--team: re-register with the stored token (after a token change)")
    link.add_argument("--token-cred", help="--team: credential store entry holding the token (default: the MCP name)")
    link.add_argument("--project-mcp-json", action="store_true",
                      help="--team: also write .mcp.json with ${GBRAIN_<PROJECT>_TOKEN} (no secret in the file)")
    link.add_argument("--no-probe", action="store_true", help="--team: skip the URL probe (offline)")
    link.add_argument("--apply", action="store_true", help="run gbrain sources add and sync, or claude mcp add with --team (needs --yes)")
    link.add_argument("--yes", action="store_true", help="the user agreed in this conversation")

    guide = sub.add_parser("install", help="guided GBrain install and init: one question, exact commands, verification (read only)")
    guide.add_argument("--choice", choices=install_guide.INSTALL_CHOICES, help="answer to the question (omit to ask it)")

    gap = sub.add_parser("gaps", help="merged work since the last captured note that has no note (git only, no LLM)")
    gap.add_argument("--repo", help="repository folder (default: current folder)")
    gap.add_argument("--ref", help="branch to check (default: origin/<default branch>)")
    gap.add_argument("--since", help="YYYY-MM-DD or a ref (default: the last commit that touched the knowledge folder)")
    gap.add_argument("--capture", choices=repo_facts.CAPTURE_MODES, help="override the repo's capture mode")
    gap.add_argument("--format", choices=("json", "text"), default="json", help="text: log lines for sync scripts")
    return parser


COMMANDS = {"status": commands.cmd_status, "collect": commands.cmd_collect, "setup": commands.cmd_setup,
            "connect": commands.cmd_connect, "install": commands.cmd_install, "gaps": commands.cmd_gaps}
USAGE = "brain_cli.py status | collect | setup | connect | install | gaps [options]"


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except _BadArgumentsExit as error:
        return emit({"ok": False, "code": "bad_args", "summary": error.message, "next": USAGE})
    if not args.command:
        return emit({"ok": False, "code": "bad_args", "summary": f"usage: {USAGE}", "next": "brain_cli.py status"})
    text_only = getattr(args, "format", "json") == "text"
    try:
        return emit(COMMANDS[args.command](args), text_only)
    except LookupError as error:
        return emit({"ok": False, "code": "not_a_repo", "summary": str(error), "next": "run inside the project repository or pass --repo"})
    except commands.NeedsConsent as error:
        return emit({"ok": False, "code": "needs_consent", "summary": str(error), "next": "ask the user, then add --yes"})
    except collect.RangeError as error:
        return emit({"ok": False, "code": "range_unknown", "summary": str(error),
                     "next": "collect --base <sha> [--head <sha>]  or  collect --commits a,b,c  or  collect --issue <N>"})
    except repo_facts.GitError as error:
        return emit({"ok": False, "code": "git_error", "summary": str(error), "next": "check the refs you passed"})


if __name__ == "__main__":
    sys.exit(main())
