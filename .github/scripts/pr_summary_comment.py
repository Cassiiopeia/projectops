#!/usr/bin/env python3
"""
pr_summary_comment.py

Posts the PR change summary as a comment. It finds the existing comment by marker and **updates** it, so pushing
commits many times keeps a single summary comment (issue #553).

Why update: if every commit added to a PR posted a new comment, the thread would be flooded with summaries and
the review comments people wrote would be buried. The marker is an HTML comment, so it is not rendered.

The input is the pr_body.md built by the provider ladder. That file is wrapped in the release-notes format (`Summary by
CodeRabbit` header + `## 릴리스 노트`), which does not suit a PR comment,
so only the body is taken out and rewrapped.

  - Output: always one JSON line (stdout). Human-readable logs go to stderr.
  - Every failure exits 0 — the summary comment must never block the PR.

Usage:
  GITHUB_TOKEN=... python3 pr_summary_comment.py --repo owner/name --pr 12 \\
      --body-file pr_body.md --app-release true
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error

import github_api
from i18n.messages import resolve_language, t

MARKER = "<!-- PROJECTOPS-AI-SUMMARY -->"
USER_AGENT = "projectops-pr-summary"

# Notice added only in repos that lead to app review (pr_summary.app_release). Helps reviewers weigh it differently.


def extract_body(raw: str) -> str:
    """Take only the item body out of the release-notes wrapper.

    The provider ladder writes items under the heading after `## Summary by CodeRabbit` (per language: `릴리스 노트`, `Release notes` ...)
    and wraps them in HTML comments. Relying on the heading text breaks with every added language,
    so the first `##` heading that is not `Summary by CodeRabbit` is taken as the body start.
    If the structure differs (another provider, etc.), the original is used as is — better than no summary.
    """
    m = re.search(r"^##[ \t]+(?!Summary by CodeRabbit)[^\n]+\n(.*?)(?:\n<!--|\Z)", raw, re.S | re.M)
    body = m.group(1) if m else raw
    # Remove surrounding HTML comment lines (left behind they only add blank lines to the comment)
    body = "\n".join(l for l in body.split("\n") if not l.strip().startswith("<!--"))
    return body.strip()


def build_comment(raw: str, app_release: bool, lang: str | None = None) -> str:
    lang = lang or resolve_language()
    parts = [MARKER, "", f"## {t('pr_summary.heading', lang)}", ""]
    if app_release:
        parts += [t("pr_summary.app_release", lang), ""]
    parts += [extract_body(raw), "", "---", t("pr_summary.footer", lang)]
    return "\n".join(parts)


def _request(method: str, url: str, token: str, payload: dict | None = None):
    return github_api.request(method, url, token, payload, user_agent=USER_AGENT)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pr_summary_comment")
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--app-release", default="false")
    args = parser.parse_args(argv)

    out = {"ok": False, "action": None, "comment_id": None, "summary": "", "next": None}
    token = os.environ.get("GITHUB_TOKEN", "")

    try:
        raw = open(args.body_file, encoding="utf-8").read()
    except Exception as e:
        out["summary"] = f"Could not read the summary file: {e}"
        sys.stderr.write(out["summary"] + "\n")
        print(json.dumps(out, ensure_ascii=False))
        return 0

    if not token:
        out["summary"] = "No GITHUB_TOKEN, so the comment was not posted"
        sys.stderr.write(out["summary"] + "\n")
        print(json.dumps(out, ensure_ascii=False))
        return 0

    body = build_comment(raw, str(args.app_release).lower() == "true")

    try:
        action, comment_id = github_api.upsert_marker_comment(
            args.repo, args.pr, token, body, MARKER, request_function=_request)
        summary = (f"Updated the existing summary comment (#{comment_id})" if action == "updated" else "Posted the summary comment")
        out.update(ok=True, action=action, comment_id=comment_id, summary=summary)
    except urllib.error.HTTPError as e:
        out["summary"] = f"Comment failed: HTTP {e.code} {e.reason}"
    except Exception as e:
        out["summary"] = f"Comment failed: {type(e).__name__}: {e}"

    sys.stderr.write(out["summary"] + "\n")
    print(json.dumps(out, ensure_ascii=False))
    return 0  # never block the PR because of the summary comment


if __name__ == "__main__":
    sys.exit(main())
