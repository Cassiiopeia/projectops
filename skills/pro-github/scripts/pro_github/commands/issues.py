"""Issue subcommands: get, get several, create, list, edit, close, reopen, search titles."""
from __future__ import annotations

from pathlib import Path

from common.emit import emit
from common.gh_client import GitHubAPIError
from pro_github.issue_followup import build_work_start_hints, rename_body_file_to_issue_number
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat, split_csv


def cmd_get_issue(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        issue = api.get_issue(args.owner, args.repo, args.number, pat)
        comments = api.get_issue_comments(args.owner, args.repo, args.number, pat) if args.with_comments else None
        return emit({
            "issue": issue,
            "comments": comments,
            "summary": f"#{issue['number']} {issue['state']} — {issue['title']}",
            "number": issue["number"],
            "title": issue["title"],
            "url": issue["url"],
            "html_url": issue["url"],
            "state": issue["state"],
            # Also put it at the top level so nobody guesses issue.labels before swapping labels
            "labels": issue.get("labels", []),
            "assignees": issue.get("assignees", []),
            "body": issue.get("body", ""),
        })
    except GitHubAPIError as e:
        return api_error(e)


def cmd_get_issues(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    issues = []
    for raw in args.numbers:
        try:
            number = int(raw)
        except ValueError:
            issues.append({"number": raw, "error": "not an integer", "code": "invalid_argument"})
            continue
        try:
            issues.append(api.get_issue(args.owner, args.repo, number, pat))
        except GitHubAPIError as e:
            issues.append({"number": number, "error": str(e), "code": f"github_api_{e.status_code}"})
    failed = [i for i in issues if "error" in i]
    if issues and len(failed) == len(issues):
        # If all fail but ok:true, the caller mistakes a missing issue for an existing one (#699)
        return emit({
            "ok": False,
            "code": "all_failed",
            "error": f"all {len(issues)} issue lookups failed",
            "count": len(issues),
            "issues": issues,
        })
    summary = f"fetched {len(issues)} issue(s)"
    if failed:
        summary = f"{len(failed)} of {len(issues)} lookups failed ({len(issues) - len(failed)} succeeded)"
    return emit({"count": len(issues), "issues": issues, "summary": summary,
                 **({"failed_count": len(failed)} if failed else {})})


def cmd_create_issue(args, api) -> int:
    # Check input before credentials. A file name typo can be reported without a PAT,
    # but checking the PAT first only says "no PAT", and the typo shows up after the PAT is filled in.
    body_path = Path(args.body_file)
    if not body_path.exists():
        return emit({
            "ok": False,
            "code": "body_file_not_found",
            "error": f"body file not found: {args.body_file}",
            "path_attempted": str(body_path.resolve()),
        })
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    body = body_path.read_text(encoding="utf-8")
    # Accept both a positional argument and --labels (so the same --labels form as other commands works)
    labels = split_csv(",".join(filter(None, (args.labels, args.labels_option))))
    assignees = split_csv(args.assignees) if args.assignees else []
    try:
        result = api.create_issue(args.owner, args.repo, args.title, body, labels, pat, assignees)
    except GitHubAPIError as e:
        return api_error(e)
    applied = result.get("assignees", [])
    missing = [a for a in assignees if a not in applied]
    out = {**result, "summary": f"created issue #{result.get('number')}", "body_length": len(body)}
    skipped_labels = out.pop("skipped_labels", [])
    if skipped_labels:
        out["label_warning"] = f"labels ignored because the repo does not have them: {', '.join(skipped_labels)}"
    if missing:
        out["assignee_warning"] = (
            f"some assignees could not be set: {', '.join(missing)} (check repo collaborators and permissions). The issue was created."
        )
    _add_created_issue_followups(out, args, body_path)
    return emit(out)


def _add_created_issue_followups(out: dict, args, body_path: Path) -> None:
    """After creation: align the local doc number (--rename-body-file) > branch name and commit template > next"""
    if args.rename_body_file:
        renamed, warning = rename_body_file_to_issue_number(body_path, out["number"])
        out["body_file_renamed_to"] = str(renamed) if renamed else None
        if warning:
            out["rename_warning"] = warning
    try:
        out.update(build_work_start_hints(out.get("title") or args.title, out["number"], out["url"]))
    except Exception as error:  # the issue is already created: a failing extra step must not lose the create response
        out.update({"branch": None, "commit_template": None, "hints_warning": f"{type(error).__name__}: {error}"})
    # Moving to in-progress uses finish-issue, which only swaps the status label (set-labels also wipes type·area labels)
    out["next"] = (f"create branch {out['branch'] or '(build it with create-branch-name)'} > "
                   f"finish-issue {args.owner} {args.repo} {out['number']} --outcome in-progress")


def cmd_list_issues(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        issues = api.list_issues(args.owner, args.repo, pat, state=args.state, labels=args.labels, limit=args.limit)
        # label/assignee filters are applied here without another API call (list_issues has the fields)
        return emit({
            "count": len(issues),
            "issues": issues,
            "summary": f"{args.owner}/{args.repo}: {len(issues)} issue(s) ({args.state})",
        })
    except GitHubAPIError as e:
        return api_error(e)


def cmd_update_issue(args, api) -> int:
    # Input first, credentials later (same reason as cmd_create_issue).
    body = None
    body_file = args.body_file or args.body_file_positional
    if body_file:
        body_path = Path(body_file)
        if not body_path.exists():
            return emit({
                "ok": False,
                "code": "body_file_not_found",
                "error": f"body file for the update not found: {body_file}",
                "path_attempted": str(body_path.resolve())
            })
        body = body_path.read_text(encoding="utf-8")

    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    labels = split_csv(args.labels) if args.labels else None
    assignees = split_csv(args.assignees) if args.assignees else None

    # If there is nothing to change, do not PATCH; say so — never misreport it as "updated" (#699)
    if all(v is None for v in (args.title, body, args.state, labels, assignees)):
        return emit({
            "ok": False,
            "code": "nothing_to_update",
            "error": "nothing to change (need one of --title/--body-file/--state/--labels/--assignees)",
        })

    try:
        result = api.update_issue(
            args.owner, args.repo, args.number, pat,
            title=args.title, body=body, state=args.state, labels=labels, assignees=assignees,
        )
        return emit({**result, "summary": f"updated #{args.number}"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_close_issue(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        # Record completed vs cancelled (not_planned) on GitHub too (#819)
        result = api.update_issue(args.owner, args.repo, args.number, pat,
                              state="closed", state_reason=args.reason)
        return emit({**result, "state_reason": args.reason,
                     "summary": f"closed #{args.number} ({args.reason})"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_reopen_issue(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        result = api.update_issue(args.owner, args.repo, args.number, pat, state="open")
        return emit({**result, "summary": f"reopened #{args.number}"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_search_issues(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    keyword = " ".join(args.keywords)
    try:
        result = api.search_issues(args.owner, args.repo, keyword, pat)
        return emit({
            "count": len(result),
            "items": result,
            "summary": f"search \"{keyword}\": {len(result)} result(s)",
        })
    except GitHubAPIError as e:
        return api_error(e)


# ── Arguments ──

def _configure_get_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("--with-comments", action="store_true")


def _configure_get_issues(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("numbers", nargs="+")


def _configure_create_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("title")
    parser.add_argument("body_file")
    # Labels may be omitted (only the template's default labels apply): as a required positional it caused bad_args when left out (#940)
    parser.add_argument("labels", nargs="?", default="", help="csv")
    parser.add_argument("--labels", dest="labels_option", default="", help="csv (same as the labels positional argument)")
    parser.add_argument("--assignees", help="assignees csv")
    parser.add_argument("--rename-body-file", dest="rename_body_file", action="store_true",
                        help="rename the body file YYYYMMDD_NNN_title so NNN becomes the real issue number")


def _configure_list_issues(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("--state", choices=["open", "closed", "all"], default="open")
    parser.add_argument("--labels", default="", help="csv; only issues that have all of them")
    parser.add_argument("--limit", type=int, default=50, help="max count (0 for all)")


def _configure_update_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    # The body file is also accepted positionally (same shape as add-comment)
    parser.add_argument("body_file_positional", nargs="?", metavar="body_file", help="body file path")
    parser.add_argument("--title")
    parser.add_argument("--state", choices=["open", "closed"])
    parser.add_argument("--labels", help="csv (replaces all)")
    parser.add_argument("--assignees", help="csv")
    parser.add_argument("--body-file", help="body file path")


def _configure_close_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("--reason", choices=["completed", "not_planned"], default="completed",
                       help="done=completed (default), cancelled=not_planned")


def _configure_reopen_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)


def _configure_search_issues(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("keywords", nargs="+")


COMMANDS = [
    Command(name="get-issue", help="get an issue", run=cmd_get_issue,
            configure=_configure_get_issue),
    Command(name="get-issues", help="get several issues at once", run=cmd_get_issues,
            configure=_configure_get_issues),
    Command(name="create-issue", help="create an issue", run=cmd_create_issue,
            configure=_configure_create_issue),
    Command(name="list-issues", help="list issues", run=cmd_list_issues,
            configure=_configure_list_issues),
    Command(name="update-issue", help="update an issue", run=cmd_update_issue,
            configure=_configure_update_issue),
    Command(name="close-issue", help="close an issue", run=cmd_close_issue,
            configure=_configure_close_issue),
    Command(name="reopen-issue", help="reopen an issue", run=cmd_reopen_issue,
            configure=_configure_reopen_issue),
    Command(name="search-issues", help="search issues", run=cmd_search_issues,
            configure=_configure_search_issues),
]
