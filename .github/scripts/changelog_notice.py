#!/usr/bin/env python3
"""Release-notes generation notice (#566) — stdlib only.

Reports in two places because their purposes differ.

  Job Summary : every time. Records which path produced the notes. **No email notification.**
  PR comment  : only when no AI could be used at all — quality actually dropped.

"Worked fine, only the path changed" (copilot exhausted -> external AI succeeded) is not reported.
A comment on every release becomes noise, and noise gets read by nobody.

The comment is found by its marker and **updated**. GitHub sends no notification for comment edits,
so email goes out only the first time.

Usage:
  changelog_notice.py --repo owner/name --pr 12 --result provider_result.json
Env: GITHUB_TOKEN (comment writing), GITHUB_STEP_SUMMARY (summary location)
"""
import argparse
import json
import os
import sys

import github_api
from i18n.messages import resolve_language, t

MARKER = "<!-- PROJECTOPS-CHANGELOG-NOTICE -->"

# Human-readable names — internal labels are not shown as is
LABELS = {
    "copilot": "Copilot",
    "openai:gemini": "Gemini",
    "openai:openai": "OpenAI",
    "openai:claude": "Claude",
    "openai:groq": "Groq",
    "openai:mistral": "Mistral",
    "openai:ollama": "Ollama",
}


def label(name, lang=None):
    if name == "commit":
        return t("changelog_notice.label.commit", lang)
    return LABELS.get(name, name)


def build_summary(result, lang=None):
    """Markdown for the Job Summary — which path it went through at a glance."""
    lang = lang or resolve_language()
    winner = result.get("provider")
    attempted = result.get("attempted") or []
    failed = set(result.get("failed") or [])

    lines = [f"## {t('changelog_notice.summary.title', lang)}", "",
             f"| {t('changelog_notice.summary.col_step', lang)} | {t('changelog_notice.summary.col_result', lang)} |", "|---|---|"]
    for name in attempted:
        mark = (t("changelog_notice.summary.used", lang) if name == winner
                else (t("changelog_notice.summary.failed", lang) if name in failed else "—"))
        lines.append(f"| {label(name, lang)} | {mark} |")
    if not attempted:
        lines.append(f"| — | {t('changelog_notice.summary.not_run', lang)} |")
    final = label(winner, lang) if winner else t("changelog_notice.summary.final_failed", lang)
    lines += ["", t("changelog_notice.summary.final", lang, label=final), ""]
    return "\n".join(lines)


def build_comment(result, lang=None):
    """For the PR comment — only when no AI could be used. None otherwise."""
    if result.get("provider") != "commit":
        return None
    failed = result.get("failed") or []
    if not failed:
        # Tried only commit from the start (working as configured) — nothing to report
        return None

    lang = lang or resolve_language()
    tried = ", ".join(label(f, lang) for f in failed)
    return "\n".join([
        MARKER,
        "",
        f"### {t('changelog_notice.comment.title', lang)}",
        "",
        t("changelog_notice.comment.tried", lang, tried=tried),
        t("changelog_notice.comment.proceeding", lang),
        "",
        t("changelog_notice.comment.option_key", lang),
        "",
        t("changelog_notice.comment.step_get_key", lang),
        t("changelog_notice.comment.step_secret", lang),
        t("changelog_notice.comment.step_name", lang),
        "",
        t("changelog_notice.comment.option_manual", lang),
        "",
        t("changelog_notice.comment.manual_body", lang),
        "",
        "---",
        "",
        t("changelog_notice.comment.footer", lang),
    ])


# Tests mock this name — upsert uses this module's request at call time
request = github_api.request


def upsert_comment(repo, pr, token, body):
    """Find the existing comment with the marker and update it, else create one. Failures only warn (never block the release)."""
    try:
        action, comment_id = github_api.upsert_marker_comment(
            repo, pr, token, body, MARKER, request_function=request)
    except OSError as e:
        print(f"⚠️ Notice comment failed ({e}) — the release continues", file=sys.stderr)
        return
    if action == "updated":
        print(f"📝 Notice comment updated (#{comment_id}) — no notification is sent")
    else:
        print("📣 Notice comment posted")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--result", default="provider_result.json")
    args = ap.parse_args()

    try:
        with open(args.result, encoding="utf-8") as f:
            result = json.load(f)
    except (OSError, ValueError) as e:
        print(f"⚠️ Could not read the result file ({e})", file=sys.stderr)
        return 0  # a failed notice must not block the release

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(build_summary(result) + "\n")
        except OSError as e:
            print(f"⚠️ Job Summary write failed ({e})", file=sys.stderr)
    else:
        print(build_summary(result))

    body = build_comment(result)
    token = os.environ.get("GITHUB_TOKEN")
    if body and token:
        upsert_comment(args.repo, args.pr, token, body)
    elif body:
        print("ℹ️ No GITHUB_TOKEN — skipping the notice comment", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
