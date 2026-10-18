#!/usr/bin/env python3
"""github_cli — github skill 전용 CLI.

GitHub API 직접 호출 도구.
서브커맨드: get-issue, get-issues, update-issue, create-pr, list-prs,
           update-pr, search-issues, add-comment, explore, secrets

사용법:
    cd skills/pro-github/scripts
    python github_cli.py <subcommand> [args]

구현은 같은 폴더의 pro_github 패키지 (cli.py 파서 조립, commands/ 주제별 서브커맨드).
이 파일은 진입점이자 의존 창구 — 핸들러는 아래 import 한 이름을 호출 시점에 여기서 찾는다.

출력 형식: 모든 서브커맨드는 stdout으로 MCP-style JSON 출력.
    {"ok": true|false, "code": "...", "summary": "...", "next": "...", ...payload}
"""
from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap — scripts/common import 가능하게 sys.path 조작 (cwd 무관 동작)
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from common.config import get_github_pat  # noqa: E402,F401  (핸들러 의존)
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402
from pro_github import cli as _cli  # noqa: E402
from pro_github.commands.actions import read_numeric_argument as _actions_int  # noqa: E402,F401  (테스트가 이 이름으로 부른다)
from pro_github.registry import Dependencies  # noqa: E402
from common.gh_client import (  # noqa: E402,F401  (핸들러 의존 — 테스트가 이 모듈 속성을 바꿔 끼운다)
    GitHubAPIError, PyNaClMissingError,
    get_issue, get_issue_comments, update_issue, create_issue, list_issues,
    add_comment, update_comment, delete_comment,
    list_labels, get_issue_labels, add_issue_labels, remove_issue_label, set_issue_labels,
    add_assignees, remove_assignees,
    list_pulls, update_pull_request, create_pull_request,
    get_pull_detail, merge_pull_request, get_branch_head,
    search_issues,
    get_user_type, list_repos, get_repo_detail, get_readme, get_languages, list_commits,
    upload_evidence_image, delete_release_asset, is_repo_private, EVIDENCE_TAG,
    list_secrets, set_secret,
    _request, get_run, get_job_log, list_failed_runs, resolve_pr_runs, resolve_branch_runs,
    list_runs, dispatch_workflow, rerun_run, wait_for_run,
)


def build_parser() -> JSONArgumentParser:
    return _cli.build_parser(Dependencies(globals()))


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
