"""finish-issue: swap the status label and close in one command. Reports how far it got even if a step fails (#941)."""
from __future__ import annotations

import urllib.error

from common.emit import emit
from common.gh_client import STATUS_LABEL_NAMES, GitHubAPIError
from common.report_comment import REPORT_COMMENT_MARKER
from pro_github.registry import Command
from pro_github.responses import missing_pat

# Detect old report comments without the marker: the 2 fixed headings of the output template (heuristic)
_REPORT_TEMPLATE_HEADINGS = ("## 개요", "## 변경 사항")

# Per outcome: (status label to apply, close reason | None=do not close)
_OUTCOMES = {
    "done": ("status: done", "completed"),
    "cancelled": ("status: cancelled", "not_planned"),
    "in-progress": ("status: in progress", None),
}


def cmd_finish_issue(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    status_label, close_reason = _OUTCOMES[args.outcome]
    steps: list[dict] = []
    try:
        current = api.get_issue_labels(args.owner, args.repo, args.number, pat)
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e), "steps": steps})

    # Swap the status label (other labels kept)
    wanted = [label for label in current if label not in STATUS_LABEL_NAMES] + [status_label]
    try:
        replaced = api.set_issue_labels(args.owner, args.repo, args.number, wanted, pat)
        if replaced.get("unchanged"):
            steps.append({"step": "labels", "ok": False, "code": "no_valid_labels",
                          "detail": f"could not replace labels: the repo has no status label {status_label}"})
        else:
            steps.append({"step": "labels", "ok": True, "labels": replaced.get("labels")})
    except GitHubAPIError as e:
        steps.append({"step": "labels", "ok": False, "code": f"github_api_{e.status_code}", "detail": str(e)})

    # Close (tried even if the label step failed: a closed issue missing a status label beats an open one with only the label changed)
    if close_reason:
        try:
            api.update_issue(args.owner, args.repo, args.number, pat, state="closed", state_reason=close_reason)
            steps.append({"step": "close", "ok": True, "reason": close_reason})
        except GitHubAPIError as e:
            steps.append({"step": "close", "ok": False, "code": f"github_api_{e.status_code}", "detail": str(e)})

    failed = [step["step"] for step in steps if not step["ok"]]
    # Closing without a report kept happening (40 closed in one batch) — warn, do not block
    warnings = _report_warnings(args, api, pat) if args.outcome == "done" else []
    return emit({
        "ok": not failed,
        "code": "finished" if not failed else "finished_partial",
        "steps": steps,
        "failed_steps": failed,
        "warnings": warnings,
        "summary": (f"#{args.number} finish: " + " > ".join(f"{s['step']} {'ok' if s['ok'] else 'failed'}" for s in steps)),
        "next": (f"retry only the failed steps: {', '.join(failed)} (run finish-issue again or close-issue)" if failed
                 else "if the report is missing, write it with pro-report and post it as a comment on this issue" if warnings else None),
    })


def is_report_comment(body: str) -> bool:
    """Whether it is a pro-report comment: has the marker or both template headings (## 개요 · ## 변경 사항)"""
    body = body or ""
    return REPORT_COMMENT_MARKER in body or all(heading in body for heading in _REPORT_TEMPLATE_HEADINGS)


def _report_warnings(args, api, pat: str) -> list[str]:
    """One warning line if there is no report comment. A failed comment lookup is also a warning (completion still proceeds)"""
    try:
        comments = api.get_issue_comments(args.owner, args.repo, args.number, pat)
    except (GitHubAPIError, urllib.error.URLError, TimeoutError, ConnectionError) as error:
        return [f"could not check for a report comment: {error}"]
    if any(is_report_comment(comment.get("body", "")) for comment in comments):
        return []
    return [f"#{args.number} has no report comment (heuristic: the marker {REPORT_COMMENT_MARKER} or the '## 개요' + '## 변경 사항' headings). "
            f"Check that a report was posted with pro-report"]


def _configure_finish_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("--outcome", choices=sorted(_OUTCOMES), default="done",
                        help="done: status: done + close / cancelled: status: cancelled + close / in-progress: label only")


COMMANDS = [
    Command(name="finish-issue", help="replace the status label and close in one step (reports partial success per step)",
            run=cmd_finish_issue, configure=_configure_finish_issue),
]
