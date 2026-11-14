"""PRs: list, edit, create (retries while head propagates), merge, details, find deploy PR, branch HEAD."""

from __future__ import annotations

import time
import urllib.parse

from common import gh_client as client
from common.github_rest.transport import _API_BASE, GitHubAPIError


def list_pulls(
    owner: str, repo: str, pat: str, state: str = "open",
) -> list[dict]:
    """List PRs."""
    items = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/pulls?state={state}&per_page=50",
        None,
        pat,
    )
    # head · base · merged_at: which branches the PR is between, and whether a closed PR was merged
    return [
        {"number": i["number"], "title": i["title"], "url": i["html_url"], "state": i["state"],
         "head": (i.get("head") or {}).get("ref"), "base": (i.get("base") or {}).get("ref"),
         "merged_at": i.get("merged_at")}
        for i in items
    ]


def update_pull_request(
    owner: str, repo: str, pr_number: int, pat: str,
    title: str | None = None, body: str | None = None,
    state: str | None = None, base: str | None = None,
) -> dict:
    """Edit a PR and return {number, url}. Used for PR body (release notes) updates, etc."""
    payload: dict = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state is not None:
        payload["state"] = state
    if base is not None:
        payload["base"] = base
    data = client._request(
        "PATCH", f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}", payload, pat
    )
    return {"number": data["number"], "url": data["html_url"]}


# Retry count and interval (seconds) for the transient error when head is not yet on GitHub right after push (#724)
_PR_HEAD_RETRIES = 3
_PR_HEAD_WAIT = 3
_sleep = time.sleep  # split out so tests can inject it and not actually wait


def create_pull_request(
    owner: str, repo: str, title: str, body: str,
    head: str, base: str, pat: str,
) -> dict:
    """Create a PR and return {number, url}.

    Right after pushing a branch, `422 PullRequest/head/invalid` can appear temporarily,
    so only that error is retried briefly. Other 422s, such as an existing PR, are not retried.
    """
    attempt = 0
    while True:
        try:
            data = client._request(
                "POST",
                f"{_API_BASE}/repos/{owner}/{repo}/pulls",
                {"title": title, "body": body, "head": head, "base": base},
                pat,
            )
            return {"number": data["number"], "url": data["html_url"]}
        except GitHubAPIError as e:
            transient = e.status_code == 422 and "head/invalid" in e.message
            if not transient or attempt >= client._PR_HEAD_RETRIES:
                raise
            attempt += 1
            client._sleep(client._PR_HEAD_WAIT)


def merge_pull_request(
    owner: str, repo: str, pr_number: int, pat: str,
    merge_method: str = "merge", commit_title: str | None = None,
    commit_message: str | None = None, sha: str | None = None,
) -> dict:
    """Merge a PR.

    merge_method: merge (default) / squash / rebase.
    Not mergeable (405), sha mismatch (409) and rebase not allowed (422) surface as GitHubAPIError,
    so the caller (CLI layer) decides the verdict from status_code.
    Returns: {sha, merged, message}.
    """
    payload: dict = {"merge_method": merge_method}
    if commit_title is not None:
        payload["commit_title"] = commit_title
    if commit_message is not None:
        payload["commit_message"] = commit_message
    if sha is not None:
        payload["sha"] = sha
    data = client._request(
        "PUT",
        f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/merge",
        payload,
        pat,
    )
    return {
        "sha": data.get("sha"),
        "merged": data.get("merged", False),
        "message": data.get("message"),
    }


def get_pull_detail(owner: str, repo: str, pr_number: int, pat: str) -> dict:
    """Extract the fields needed for the merge verdict from a single PR's details.

    list_pulls lacks body and mergeable_state, so it is fetched separately for deploy-status checks.
    """
    pr = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}", None, pat)
    return {
        "number": pr["number"],
        "title": pr.get("title"),
        "state": pr["state"],
        "merged": pr.get("merged", False),
        # Branch name (same key name as list_pulls, #1180)
        "base": (pr.get("base") or {}).get("ref"),
        "head": (pr.get("head") or {}).get("ref"),
        "mergeable_state": pr.get("mergeable_state"),
        "body": pr.get("body") or "",
        "head_sha": pr.get("head", {}).get("sha"),
        "url": pr["html_url"],
        "created_at": pr.get("created_at"),
        "updated_at": pr.get("updated_at"),
    }


# Bot branch prefixes excluded from deploy PR candidates. Dependency bot PRs also target the default branch (main),
# so looking at base alone mistakes them for the deploy PR and "reuse existing PR" overwrites that PR's body.
_BOT_HEAD_PREFIXES = ("dependabot/", "renovate/")


def find_open_pr_by_base(owner: str, repo: str, base: str, pat: str, head: str | None = None) -> dict | None:
    """Return the details of the one deploy PR among open PRs into base. None if none.

    Used to find the deploy PR automatically when deploy-status is called without --pr.
    - With head, only PRs from that branch are picked (most precise).
    - Without head, pick the first PR excluding dependency bots (dependabot/, renovate/).
    """
    items = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/pulls?state=open&base={base}&per_page=50",
        None, pat,
    )
    for it in items or []:
        ref = (it.get("head") or {}).get("ref", "")
        if head:
            if ref != head:
                continue
        elif ref.startswith(_BOT_HEAD_PREFIXES):
            continue
        return client.get_pull_detail(owner, repo, it["number"], pat)
    return None


def get_ahead_by(owner: str, repo: str, base: str, head: str, pat: str) -> int | None:
    """Number of commits head is ahead of base (is there anything to release). None if it cannot compare (#945)"""
    pair = f"{urllib.parse.quote(base, safe='/')}...{urllib.parse.quote(head, safe='/')}"
    try:
        data = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/compare/{pair}", None, pat)
    except GitHubAPIError:
        return None
    ahead = data.get("ahead_by")
    return ahead if isinstance(ahead, int) else None


def get_branch_head(owner: str, repo: str, branch: str, pat: str) -> str | None:
    """Return the branch HEAD SHA. None if the branch does not exist (404 absorbed as None)."""
    enc = urllib.parse.quote(branch, safe="/")
    try:
        ref = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/git/ref/heads/{enc}", None, pat)
    except GitHubAPIError as e:
        if e.status_code == 404:
            return None
        raise
    return ref.get("object", {}).get("sha")
