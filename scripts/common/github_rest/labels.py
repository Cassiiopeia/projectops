"""Labels: Korean/English alias mapping, list, add, remove one, replace all."""

from __future__ import annotations

import urllib.parse

from common import gh_client as client
from common.github_rest.transport import _API_BASE


# Korean status labels and the English standard labels (#776) are the same labels. During the transition, map to the name present in the repo.
LABEL_ALIAS_GROUPS = [
    ("작업전", "status: todo"),
    ("작업중", "status: in progress"),
    ("담당자확인", "status: needs review"),
    ("피드백", "status: feedback"),
    ("작업완료", "status: done"),
    ("보류", "status: on hold"),
    ("취소", "status: cancelled"),
    ("긴급", "priority: urgent"),
    ("문서", "documentation"),
]

# All status label names (Korean and English, the first 7 pairs above): done handling and label-replace warnings treat only these as status
STATUS_LABEL_NAMES = frozenset(name for group in LABEL_ALIAS_GROUPS[:7] for name in group)


def resolve_label_aliases(requested: list[str], existing) -> list[str]:
    """Return the requested labels, replacing ones missing from the repo with an alias (Korean/English) that exists in the repo.

    Names already in the repo stay as is (exact name wins). Without an alias, keep the original so
    the caller's existing 'filter out missing labels' path still works. Duplicates are removed.
    """
    existing = set(existing)
    out: list[str] = []
    for name in requested:
        resolved = name
        if name not in existing:
            for group in LABEL_ALIAS_GROUPS:
                if name in group:
                    resolved = next((a for a in group if a in existing), name)
                    break
        if resolved not in out:
            out.append(resolved)
    return out


def list_labels(owner: str, repo: str, pat: str) -> list[str]:
    """Return the repo's label names."""
    items = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/labels?per_page=100", None, pat)
    return [item["name"] for item in items]


def get_issue_labels(owner: str, repo: str, issue_number: int, pat: str) -> list[str]:
    """Return the label names currently on an issue/PR."""
    items = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/labels?per_page=100",
        None,
        pat,
    )
    return [item["name"] for item in items]


def add_issue_labels(owner: str, repo: str, issue_number: int, labels: list[str], pat: str) -> list[str]:
    """Add labels to an issue/PR (both are issues in the GitHub API) (not an overwrite).

    The GitHub API treats PRs as issues, so `/issues/{n}/labels` works for them.
    Labels missing from the repo are filtered first to avoid 422.
    Returns: list of all label names currently on the issue/PR.
    With no labels to apply, return the current labels without POSTing (never misreport an empty list, #698).
    """
    if not labels:
        return client.get_issue_labels(owner, repo, issue_number, pat)
    existing = set(client.list_labels(owner, repo, pat))
    labels = client.resolve_label_aliases(labels, existing)
    filtered = [l for l in labels if l in existing]
    if not filtered:
        return client.get_issue_labels(owner, repo, issue_number, pat)
    items = client._request(
        "POST",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/labels",
        {"labels": filtered},
        pat,
    )
    return [item["name"] for item in items]


def remove_issue_label(
    owner: str, repo: str, issue_number: int, name: str, pat: str,
) -> dict:
    """Remove just one label from an issue (other labels kept).

    The label name goes into the URL path, so always encode it (Korean labels like `작업중`).
    If the issue does not have that label, it returns 404, so the caller handles it idempotently.
    Returns: list of label names left on the issue after removal.
    """
    # Korean/English alias: remove using the name actually on the issue (#776)
    for group in LABEL_ALIAS_GROUPS:
        if name in group:
            on_issue = client.get_issue_labels(owner, repo, issue_number, pat)
            if name not in on_issue:
                name = next((a for a in group if a in on_issue), name)
            break
    enc = urllib.parse.quote(name, safe="")
    items = client._request(
        "DELETE",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/labels/{enc}",
        None,
        pat,
    )
    return {"labels": [item["name"] for item in items]}


def set_issue_labels(
    owner: str, repo: str, issue_number: int, labels: list[str], pat: str,
) -> dict:
    """Replace an issue's labels entirely (remove all existing labels, then apply the new array).

    An explicit empty array removes all labels. Labels missing from the repo are filtered first to avoid 422.
    But if labels were requested and all were filtered out as missing, do not PUT;
    PUTting an empty array silently wipes existing labels (status labels, etc.) (#698).
    Returns: {"labels": labels after replacement (or kept unchanged), "skipped": filtered labels, "unchanged": whether nothing changed}.
    """
    skipped: list[str] = []
    if labels:
        existing = set(client.list_labels(owner, repo, pat))
        labels = client.resolve_label_aliases(labels, existing)
        skipped = [l for l in labels if l not in existing]
        labels = [l for l in labels if l in existing]
        if not labels:
            # Data preservation: if there is nothing to apply, leave existing labels alone
            current = client.get_issue_labels(owner, repo, issue_number, pat)
            return {"labels": current, "skipped": skipped, "unchanged": True}
    items = client._request(
        "PUT",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/labels",
        {"labels": labels},
        pat,
    )
    return {"labels": [item["name"] for item in items], "skipped": skipped, "unchanged": False}
