#!/usr/bin/env python3
"""prefs_cli — personal preferences lookup CLI shared by every skill.

Usage: python scripts/prefs_cli.py resolve --skill pro-report [--repo owner/repo]
Without --repo, the repo layer is found from the current directory's origin remote.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402
from common.emit import emit  # noqa: E402
from common.preferences import detect_repo, resolve  # noqa: E402


def cmd_resolve(args) -> int:
    owner = repo = None
    if args.repo:
        if "/" not in args.repo:
            return emit({"ok": False, "code": "bad_repo", "error": "--repo must be owner/repo"})
        owner, repo = args.repo.split("/", 1)
    else:
        owner, repo = detect_repo()
    result = resolve(args.skill, owner, repo, load=True)
    keys = ", ".join(sorted(result["values"])) or "none (defaults)"
    payload = {**result, "repo": f"{owner}/{repo}" if owner else None,
               "summary": f"{args.skill} settings: {keys}"}
    if result.get("config_status") == "unreadable":
        # Silently falling back to defaults on a broken config hides why settings are ignored.
        # Defaults still work, so keep ok and report only through code.
        payload.update(code="config_unreadable",
                       summary=f"could not read config.json, using defaults ({args.skill})",
                       next="fix the JSON syntax in ~/.projectops/config/config.json")
    return emit(payload)


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="prefs_cli", description="Look up personal preferences")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("resolve", help="Final settings and their sources for one skill")
    p.add_argument("--skill", required=True)
    p.add_argument("--repo", default=None)
    p.set_defaults(func=cmd_resolve)
    return parser


if __name__ == "__main__":
    sys.exit(run_cli(build_parser()))
