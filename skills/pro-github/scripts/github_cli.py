#!/usr/bin/env python3
"""github_cli — CLI for the github skill.

Calls the GitHub API directly.
Subcommands: get-issue, get-issues, update-issue, create-pr, list-prs,
           update-pr, search-issues, add-comment, explore, secrets

Usage:
    cd skills/pro-github/scripts
    python github_cli.py <subcommand> [args]

Implemented in the pro_github package in this folder (cli.py builds the parser, commands/ holds subcommands by topic).
This file is the entry point and dependency gateway — handlers look up the names imported below here at call time.

Output: every subcommand prints MCP-style JSON to stdout.
    {"ok": true|false, "code": "...", "summary": "...", "next": "...", ...payload}
"""
from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap — adjust sys.path so scripts/common can be imported (works from any cwd)
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from common.config import get_github_pat  # noqa: E402,F401  (handler dependency)
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402
from pro_github import cli as _cli  # noqa: E402
from pro_github.commands.actions import read_numeric_argument as _actions_int  # noqa: E402,F401  (tests call it by this name)
from pro_github.registry import Dependencies  # noqa: E402
from common.gh_client import (  # noqa: E402,F401  (handler dependency — tests swap these module attributes)
    GitHubAPIError, PyNaClMissingError,
    get_issue, get_issue_comments, update_issue, create_issue, list_issues,
    add_comment, update_comment, delete_comment,
    list_labels, get_issue_labels, add_issue_labels, remove_issue_label, set_issue_labels,
    add_assignees, remove_assignees,
    list_pulls, update_pull_request, create_pull_request,
    get_pull_detail, merge_pull_request, get_branch_head,
    search_issues,
    get_user_type, list_repos, get_repo_detail, get_readme, get_languages, list_commits, create_repo,
    update_repo_visibility, delete_repo, list_tree_paths,
    upload_evidence_image, delete_release_asset, is_repo_private, EVIDENCE_TAG,
    list_secrets, set_secret,
    _request, get_run, get_job_log, list_failed_runs, resolve_pr_runs, resolve_branch_runs,
    list_runs, dispatch_workflow, rerun_run, wait_for_run, wait_for_runs, cancel_run,
    ReleaseAssetLimitError,
)


def build_parser() -> JSONArgumentParser:
    return _cli.build_parser(Dependencies(globals()))


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
