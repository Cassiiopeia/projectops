"""GitHub facts for an issue record note: issue (title, labels, dates, body), comments (report flagged), PR (body, merge)
Read only, the user's own PAT from the projectops config (never printed). Bodies are source material the agent
summarizes; they are truncated and never copied into a note as is.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from . import credentials, http_client

API_ROOT = "https://api.github.com"
TIMEOUT_SECONDS = 20
BODY_CHARS = 4000               # issue and PR body excerpt
COMMENT_CHARS = 3000            # one comment excerpt
COMMENT_LIMIT = 30              # newest comments kept
REPORT_MARKER = "<!-- projectops:report -->"
REPORT_HEADINGS = (("## 개요", "## 변경 사항"), ("## Overview", "## Changes"))
ISSUE_REFERENCE = re.compile(r"(?<![\w/])#(\d{1,6})\b")


def read_pat(remote_slug: str | None) -> str | None:
    """GITHUB_PAT env > github.repos[] pat for this repo > github.global_pat > github.global_pat_cred (credential store)"""
    if os.environ.get("GITHUB_PAT"):
        return os.environ["GITHUB_PAT"]
    data, _ = credentials.load_config()
    github = (data or {}).get("github") if isinstance(data, dict) else None
    github = github if isinstance(github, dict) else {}
    for repo in github.get("repos") or []:
        if isinstance(repo, dict) and remote_slug and f"{repo.get('owner')}/{repo.get('repo')}".lower() == remote_slug.lower() \
                and repo.get("pat"):
            return str(repo["pat"])
    if github.get("global_pat"):
        return str(github["global_pat"])
    reference = github.get(credentials.GITHUB_PAT_REFERENCE_KEY)
    if reference:
        try:
            return credentials.read_secret(str(reference), "token")
        except credentials.CredentialError:
            return None
    return None


def _get(path: str, pat: str):
    request = urllib.request.Request(API_ROOT + path, headers={"Authorization": f"Bearer {pat}", "User-Agent": http_client.USER_AGENT,
                                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _excerpt(text: str | None, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + f"\n[... {len(text) - limit} more characters]"


def is_report_comment(body: str) -> bool:
    return REPORT_MARKER in body or any(all(heading in body for heading in pair) for pair in REPORT_HEADINGS)


def fetch(remote_slug: str | None, issue: int | None, pr_number: int | None, branch: str | None) -> dict:
    """{fetched, issue, comments, pr, related_issues, metadata} or {fetched: false, reason, next}"""
    if not remote_slug:
        return {"fetched": False, "reason": "no GitHub origin remote"}
    pat = read_pat(remote_slug)
    if not pat:
        return {"fetched": False, "reason": "no GitHub PAT in the projectops config",
                "next": "read the issue, comments and PR with pro-github get-issue --with-comments and get-pr instead"}
    result: dict = {"fetched": True}
    metadata: dict = {}
    texts: list[str] = []
    try:
        if issue:
            data = _get(f"/repos/{remote_slug}/issues/{issue}", pat)
            labels = [label.get("name") for label in data.get("labels") or [] if isinstance(label, dict)]
            result["issue"] = {"title": data.get("title"), "state": data.get("state"), "labels": labels,
                               "opened": (data.get("created_at") or "")[:10] or None,
                               "closed": (data.get("closed_at") or "")[:10] or None,
                               "url": data.get("html_url"), "body": _excerpt(data.get("body"), BODY_CHARS)}
            metadata.update({"issue_title": data.get("title"), "issue_labels": labels,
                             "issue_opened": result["issue"]["opened"], "issue_closed": result["issue"]["closed"]})
            texts.append(data.get("body") or "")
            comments = _get(f"/repos/{remote_slug}/issues/{issue}/comments?per_page=100", pat)
            kept = comments[-COMMENT_LIMIT:] if isinstance(comments, list) else []
            result["comments"] = [{"author_is_bot": (comment.get("user") or {}).get("type") == "Bot",
                                   "created": (comment.get("created_at") or "")[:10],
                                   "is_report": is_report_comment(comment.get("body") or ""),
                                   "url": comment.get("html_url"),
                                   "body": _excerpt(comment.get("body"), COMMENT_CHARS)} for comment in kept]
            texts += [comment.get("body") or "" for comment in kept]
        pull = None
        if pr_number:
            pull = _get(f"/repos/{remote_slug}/pulls/{pr_number}", pat)
        elif branch:
            owner = remote_slug.split("/")[0]
            listed = _get(f"/repos/{remote_slug}/pulls?state=all&per_page=5&head={urllib.parse.quote(owner + ':' + branch)}", pat)
            pull = listed[0] if isinstance(listed, list) and listed else None
        if pull:
            result["pr"] = {"number": pull.get("number"), "url": pull.get("html_url"), "title": pull.get("title"),
                            "merged": bool(pull.get("merged_at")), "merged_at": (pull.get("merged_at") or "")[:10] or None,
                            "merge_commit": (pull.get("merge_commit_sha") or "")[:12] or None,
                            "base": (pull.get("base") or {}).get("ref"), "body": _excerpt(pull.get("body"), BODY_CHARS)}
            metadata.update({"pr": pull.get("number"), "pr_url": pull.get("html_url")})
            texts.append(pull.get("body") or "")
    except urllib.error.HTTPError as error:
        return {"fetched": False, "reason": f"GitHub API {error.code}",
                "next": "check the PAT (401) or access (403/404); or read it with pro-github get-issue --with-comments"}
    except (urllib.error.URLError, OSError, ValueError) as error:
        return {"fetched": False, "reason": http_client.mask_text(f"GitHub API unreachable: {error}", [pat])}
    related = sorted({int(number) for text in texts for number in ISSUE_REFERENCE.findall(text)} - {issue or 0})
    result["related_issues"] = related[:20]
    metadata["related_issues"] = related[:20]
    result["metadata"] = {key: value for key, value in metadata.items() if value not in (None, "", [])}
    return result
