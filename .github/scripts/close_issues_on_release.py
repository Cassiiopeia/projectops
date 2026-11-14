#!/usr/bin/env python3
"""Close finished issues when a release ships (#771) — stdlib only.

The policy "finished issues get a label but stay open" came from Projects sync being label-based.
As a result open issues pile up and visitors see an abandoned project. So instead of people closing them,
**the workflow closes them when a release ships.** The label still marks completion.

Rules
  - Only issue URLs referenced by commit messages in the release range (before..after).
  - Only issues with a done label (status: done / 작업완료) are closed. No label -> untouched.
  - Already closed issues and PRs are skipped.
  - Runs only when close_on_release in version.yml is true. Without the key (existing installs) it does nothing.

Usage:
  close_issues_on_release.py --repo owner/name --before SHA --after SHA [--dry-run]
Env: GITHUB_TOKEN
"""
import argparse
import os
import re
import subprocess
import sys
import urllib.error

import github_api

API = github_api.API_ROOT
DONE_LABELS = {"status: done", "작업완료"}


def close_on_release_enabled(version_yml_text: str) -> bool:
    """Read close_on_release from version.yml. False without the key (protects existing installs)."""
    m = re.search(r"^\s+close_on_release:\s*[\"']?(true|false)[\"']?", version_yml_text, re.M)
    return bool(m) and m.group(1) == "true"


def issue_numbers_from_commits(messages: list[str], repo: str) -> list[int]:
    """Collect this repo's issue URL numbers from commit messages (order kept, duplicates removed)."""
    pat = re.compile(rf"github\.com/{re.escape(repo)}/issues/(\d+)", re.I)
    seen: list[int] = []
    for msg in messages:
        for n in pat.findall(msg):
            if int(n) not in seen:
                seen.append(int(n))
    return seen


def should_close(issue: dict) -> bool:
    """Should it close: an issue (not a PR), open, and with a done label."""
    if "pull_request" in issue or issue.get("state") != "open":
        return False
    names = {(l["name"] if isinstance(l, dict) else l) for l in issue.get("labels", [])}
    return bool(names & DONE_LABELS)


def _request(method: str, url: str, token: str, payload: dict | None = None):
    return github_api.request(method, url, token, payload, user_agent="projectops-close-on-release")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()


def previous_release_tag(after: str) -> str:
    """Most recent tag reachable from after that does not point at after itself (the previous release).

    When woken by dispatch there is no before (#551). Looking only at the last commit would see only the
    README version commit appended after the release, so the range runs from the previous release tag to now.
    """
    head = _git("rev-parse", after)
    for tag in _git("tag", "--merged", after, "--sort=-creatordate").splitlines():
        if _git("rev-list", "-n", "1", tag) != head:
            return tag
    return ""


def release_range(before: str, after: str) -> str:
    if before and set(before) != {"0"}:
        return f"{before}..{after}"
    tag = previous_release_tag(after)
    return f"{tag}..{after}" if tag else f"{after}~1..{after}"


def commit_messages(before: str, after: str) -> list[str]:
    out = _git("log", release_range(before, after), "--format=%B%x00")
    return [m for m in out.split("\x00") if m.strip()]


def release_pr_messages(repo: str, after: str, token: str, lookback: int = 15) -> list[str] | None:
    """Commit messages of the merged release PR. None if not found.

    When woken by dispatch (#551) there is no before. Guessing the range from tags is wrong then: the release workflow
    **creates this release's tag first** and then wakes us, so this tag is taken as the "previous release" and the range becomes the one
    README commit appended after the release (#791, found in a real Actions e2e). So walk back from HEAD to find the merged PR
    (base = default branch) linked to recent commits and use that PR's commits. Independent of tags and merge method (merge, squash,
    rebase). Bot commits appended after the release are not linked to a PR and are skipped.
    """
    for sha in _git("rev-list", f"--max-count={lookback}", after).splitlines():
        prs = _request("GET", f"{API}/repos/{repo}/commits/{sha}/pulls", token) or []
        for pr in prs:
            base = pr.get("base") or {}
            if not pr.get("merged_at") or base.get("ref") != (base.get("repo") or {}).get("default_branch", base.get("ref")):
                continue
            if (pr.get("head") or {}).get("ref") == base.get("ref"):
                continue
            messages: list[str] = []
            for page in (1, 2, 3):  # up to 300 commits per PR
                chunk = _request("GET", f"{API}/repos/{repo}/pulls/{pr['number']}/commits?per_page=100&page={page}", token) or []
                messages += [c["commit"]["message"] for c in chunk]
                if len(chunk) < 100:
                    break
            return messages
    return None


def release_messages(repo: str, before: str, after: str, token: str) -> list[str]:
    """Commit messages of the release range. push uses before..after, dispatch uses the release PR, else a tag range."""
    if before and set(before) != {"0"}:
        return commit_messages(before, after)
    try:
        found = release_pr_messages(repo, after, token)
        if found is not None:
            return found
    except Exception as e:  # a failed lookup must not block the release
        print(f"Release PR lookup failed ({type(e).__name__}), using the tag range instead")
    return commit_messages(before, after)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--before", default="")
    ap.add_argument("--after", required=True)
    ap.add_argument("--version-file", default="version.yml")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    try:
        text = open(a.version_file, encoding="utf-8").read()
    except OSError:
        text = ""
    if not close_on_release_enabled(text):
        print("close_on_release is not on, skipping.")
        return 0

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("No GITHUB_TOKEN, skipping.")
        return 0

    numbers = issue_numbers_from_commits(release_messages(a.repo, a.before, a.after, token), a.repo)
    print(f"Issues referenced in the release range: {numbers}")
    closed = []
    for n in numbers:
        try:
            issue = _request("GET", f"{API}/repos/{a.repo}/issues/{n}", token)
        except urllib.error.HTTPError as e:
            print(f"#{n}: lookup failed ({e.code}), skipped")
            continue
        if not should_close(issue):
            print(f"#{n}: skipped (not an open issue, or no done label)")
            continue
        if a.dry_run:
            print(f"#{n}: [dry-run] would close")
            continue
        try:
            _request("PATCH", f"{API}/repos/{a.repo}/issues/{n}", token,
                     {"state": "closed", "state_reason": "completed"})
            closed.append(n)
            print(f"#{n}: closed")
        except urllib.error.HTTPError as e:
            print(f"#{n}: close failed ({e.code})")
    print(f"Closed issues: {closed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
