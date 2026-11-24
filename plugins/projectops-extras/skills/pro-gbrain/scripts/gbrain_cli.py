#!/usr/bin/env python3
"""gbrain_cli: attach a repository to GBrain in one flow (repo only, own brain, or a team brain on a brain server).
Output is always JSON (ok, code, summary, next). detect, plan, status and verify-free reads change nothing;
add, repair and share write only with --apply --yes; remove also needs --confirm <project> and never deletes data.
extras installs only its own folder, so standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gbrain_ops import commands, common, context, credentials, management_parser  # noqa: E402

# Same rule as scripts/common/emit.py: one unencodable char on a cp949 console must not kill the CLI
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

USAGE = "gbrain_cli.py manage | triggers | event | detect | plan | add | repair | status | verify | share | remove [options]"


class _BadArgumentsExit(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class JsonArgumentParser(argparse.ArgumentParser):
    """Parser that returns argument errors as JSON instead of stderr"""

    def error(self, message):
        raise _BadArgumentsExit(message)


def emit(payload: dict) -> int:
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()
    return 0 if payload["ok"] else 1


def _add_flow_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", help="repository folder (default: current folder)")
    parser.add_argument("--project", help="project key (default: registry match, else the folder name)")
    parser.add_argument("--capture", help="pro-brain capture mode (default: issue-end)")
    parser.add_argument("--claude-md", dest="claude_md", choices=("add", "decline"), help="rule block (default: add)")
    parser.add_argument("--contact", help="who issues teammate tokens, shown in the repo switch")
    parser.add_argument("--mcp-url", dest="mcp_url", help="team brain URL when there is no provisioner (manual server)")
    parser.add_argument("--mcp-name", dest="mcp_name", help="team brain MCP name when there is no provisioner, e.g. gbrain-myapp")
    parser.add_argument("--no-first-sync", dest="no_first_sync", action="store_true", help="skip the first sync run")
    parser.add_argument("--steps", help="comma-separated subset of steps, e.g. local,verify")
    parser.add_argument("--apply", action="store_true", help="write (needs --yes)")
    parser.add_argument("--yes", action="store_true", help="the user agreed in this conversation")


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="gbrain_cli.py", description="attach a repository to GBrain")
    sub = parser.add_subparsers(dest="command", parser_class=JsonArgumentParser)

    detect = sub.add_parser("detect", help="repo, project key, own brain, provisioner and the one question (read only)")
    detect.add_argument("--repo")
    detect.add_argument("--project")

    plan = sub.add_parser("plan", help="steps for a mode, with the server and repo previews (read only)")
    plan.add_argument("--mode", choices=context.MODES, required=True)
    _add_flow_options(plan)

    add = sub.add_parser("add", help="run the steps not finished yet (needs --apply --yes)")
    add.add_argument("--mode", choices=context.MODES, required=True)
    _add_flow_options(add)

    repair = sub.add_parser("repair", help="re-run every step of the recorded mode (idempotent, needs --apply --yes)")
    repair.add_argument("--mode", choices=context.MODES, help="default: the recorded mode")
    _add_flow_options(repair)

    status = sub.add_parser("status", help="every team brain: registry, server health, this machine's sync (read only)")
    status.add_argument("--project")

    verify = sub.add_parser("verify", help="end-to-end check with a throwaway read-only token (revoked at the end)")
    verify.add_argument("--project", required=True)

    share = sub.add_parser("share", help="issue a read-only teammate token into a private message file")
    share.add_argument("--project", required=True)
    share.add_argument("--member", help="teammate name (token label)")
    share.add_argument("--apply", action="store_true")
    share.add_argument("--yes", action="store_true")

    remove = sub.add_parser("remove", help="detach on this machine (disable sync, flag the registry); never deletes data")
    remove.add_argument("--project", required=True)
    remove.add_argument("--apply", action="store_true")
    remove.add_argument("--confirm", help="the project key, typed by the user")
    COMMANDS.update(management_parser.register(sub))
    return parser


COMMANDS = {"detect": commands.cmd_detect, "plan": commands.cmd_plan, "add": commands.cmd_add,
            "repair": commands.cmd_repair, "status": commands.cmd_status, "verify": commands.cmd_verify,
            "share": commands.cmd_share, "remove": commands.cmd_remove}


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except _BadArgumentsExit as error:
        return emit({"ok": False, "code": "bad_args", "summary": error.message, "next": USAGE})
    if not args.command:
        return emit({"ok": False, "code": "bad_args", "summary": f"usage: {USAGE}", "next": "gbrain_cli.py detect"})
    try:
        return emit(COMMANDS[args.command](args))
    except commands.NeedsConsent as error:
        return emit({"ok": False, "code": "needs_consent", "summary": str(error), "next": "ask the user, then add --apply --yes"})
    except credentials.CredentialError as error:
        return emit({"ok": False, "code": error.code, "summary": error.message, "next": error.next_hint})
    except OSError as error:
        return emit({"ok": False, "code": "io_error", "summary": str(error), "next": "check file paths and permissions"})
    except common.StepError as error:
        return emit({"ok": False, "code": error.code, "summary": error.message, "next": error.next_step, **error.details})


if __name__ == "__main__":
    sys.exit(main())
