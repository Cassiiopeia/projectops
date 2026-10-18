"""GitHub REST API 클라이언트 — urllib 표준 라이브러리만 사용.

구현은 common/github_rest/ 모듈 8개: transport(요청·오류), labels, issues, pulls, repository, actions, actions_secrets, evidence.
호출부는 `from common.gh_client import X` / `gh_client.X` 그대로 쓴다 (이름 전부 여기서 재노출).
모듈 사이 호출은 이 모듈 경유 — 테스트가 여기 속성을 바꿔 끼우면 내부 호출에도 반영.
"""

from __future__ import annotations

from common.github_rest.transport import (  # noqa: F401
    _API_BASE, _DEFAULT_TIMEOUT,
    GitHubAPIError, GitHubNetworkError, PyNaClMissingError,
    _StripAuthRedirect, _opener, _error_message,
    _request, request_json, _upload_request,
)
from common.github_rest.labels import (  # noqa: F401
    LABEL_ALIAS_GROUPS, resolve_label_aliases,
    list_labels, get_issue_labels, add_issue_labels, remove_issue_label, set_issue_labels,
)
from common.github_rest.issues import (  # noqa: F401
    create_issue, update_issue, get_issue, get_issue_comments, list_issues, search_issues,
    add_assignees, remove_assignees,
    add_comment, update_comment, delete_comment,
)
from common.github_rest.repository import (  # noqa: F401
    get_user_type, list_repos, get_repo_detail, get_readme, get_languages, list_commits,
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
)
from common.github_rest.evidence import (  # noqa: F401
    EVIDENCE_TAG, _RENDERABLE,
    ensure_evidence_release, _asset_name, upload_evidence_image, delete_release_asset,
)
