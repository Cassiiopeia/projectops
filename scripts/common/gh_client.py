"""GitHub REST API client — urllib standard library only.

Implemented in 8 modules under common/github_rest/: transport (requests, errors), labels, issues, pulls, repository, actions, actions_secrets, evidence.
Callers keep using `from common.gh_client import X` / `gh_client.X` (every name is re-exported here).
Calls between modules go through this module — when a test swaps an attribute here, internal calls see it too.
"""

from __future__ import annotations

from common.github_rest.transport import (  # noqa: F401
    _API_BASE, _DEFAULT_TIMEOUT,
    GitHubAPIError, GitHubNetworkError, PyNaClMissingError,
    _StripAuthRedirect, _opener, _error_message,
    _request, request_json, _upload_request,
)
from common.github_rest.labels import (  # noqa: F401
    LABEL_ALIAS_GROUPS, STATUS_LABEL_NAMES, resolve_label_aliases,
    list_labels, get_issue_labels, add_issue_labels, remove_issue_label, set_issue_labels,
)
from common.github_rest.issues import (  # noqa: F401
    create_issue, update_issue, get_issue, get_issue_comments, list_issues, search_issues,
    add_assignees, remove_assignees,
    add_comment, update_comment, delete_comment,
)
from common.github_rest.repository import (  # noqa: F401
    get_user_type, list_repos, get_repo_detail, get_readme, get_languages, list_commits,
    get_authenticated_login, create_repo, update_repo_visibility, delete_repo, list_tree_paths,
    is_repo_private,
)
from common.github_rest.actions_secrets import (  # noqa: F401
    list_secrets, _load_nacl_public, _encrypt_secret, set_secret,
)
from common.github_rest.pulls import (  # noqa: F401
    list_pulls, update_pull_request, create_pull_request, merge_pull_request,
    get_pull_detail, find_open_pr_by_base, get_branch_head, get_ahead_by,
    _PR_HEAD_RETRIES, _PR_HEAD_WAIT, _sleep, _BOT_HEAD_PREFIXES,
)
from common.github_rest.actions import (  # noqa: F401
    _run_summary, get_run, get_job_log, list_failed_runs, resolve_pr_runs, resolve_branch_runs,
    list_runs, dispatch_workflow, rerun_run, wait_for_run, wait_for_runs, cancel_run,
)
from common.github_rest.evidence import (  # noqa: F401
    EVIDENCE_TAG, _RENDERABLE, ReleaseAssetLimitError, is_asset_limit_error, evidence_tag_candidates,
    ensure_evidence_release, _asset_name, upload_evidence_image, delete_release_asset,
)
