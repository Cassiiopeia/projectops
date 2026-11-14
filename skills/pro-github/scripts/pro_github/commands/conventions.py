"""Network-free subcommands: issue doc path, title normalization, branch name, commit template."""
from __future__ import annotations

from common.emit import emit
from pro_github.registry import Command


def _commit_type_arg(value: str) -> str:
    from common.gh_branch import commit_type_arg
    return commit_type_arg(value)


def _date_arg(value: str) -> str:
    from common.gh_branch import date_arg
    return date_arg(value)


def cmd_get_output_path(args, api) -> int:
    # Path rules are owned only by common/paths.py (#525·#623) — issue docs are not assembled by hand either (#822).
    # A new issue has no number yet, so use a serial number instead of borrowing the current branch's issue number.
    from common.gh_branch import strip_issue_decorations
    from common.paths import resolve_output_path
    # No emoji or [tags] in file names — keeps a tag glued to the title from becoming `BugSkills_...`
    # Positional allowed: both "issue <title>" and "<title>" (calls passing the title positionally hit bad_args, #1063)
    words = list(args.words)
    if words and words[0] == "issue":
        words = words[1:]
    raw_title = args.title or " ".join(words)
    title = strip_issue_decorations(raw_title) if raw_title else None
    return emit(resolve_output_path("issue", title, use_issue_number=False, root=args.root))


def cmd_normalize_title(args, api) -> int:
    from common.title import normalize
    result = normalize(" ".join(args.title))
    return emit({"normalized": result, "summary": result})


def read_branch_name_values(values: list[str]) -> tuple:
    """[title, number] · [number, title] · [owner, repo, title, number] > (title, number) | None (owner repo up front is accepted like other commands)"""
    if len(values) == 4 and values[3].isdigit():
        return values[2], int(values[3])
    if len(values) == 2 and values[1].isdigit():
        return values[0], int(values[1])
    if len(values) == 2 and values[0].isdigit():
        return values[1], int(values[0])
    return None


def cmd_create_branch_name(args, api) -> int:
    from common.gh_branch import create_branch_name
    parsed = read_branch_name_values(args.values)
    if parsed is None:
        return emit({"ok": False, "code": "bad_args", "error": f"could not read a title and issue number: {args.values}",
                     "usage": "create-branch-name <title> <number> (or <owner> <repo> <title> <number>)"})
    issue_title, issue_number = parsed
    name = create_branch_name(issue_title, issue_number, args.date)
    return emit({"branch": name, "issue_number": issue_number, "summary": name})


def cmd_get_commit_template(args, api) -> int:
    # Same resolution path as the commit skill — so the template shown after issue creation matches the one at commit time
    from common.commit_style import render_for_issue, resolve_for_repo
    _, style = resolve_for_repo(getattr(args, "repo_root", None))
    template = render_for_issue(style, issue_title=args.issue_title, issue_url=args.issue_url,
                                commit_type=getattr(args, "commit_type", None),
                                scope=getattr(args, "scope", None) or "")
    return emit({"template": template, "source": style["source"], "warnings": style["warnings"],
                 "summary": template})


# ── Arguments ──

def _configure_get_output_path(parser) -> None:
    parser.add_argument("words", nargs="*", metavar="[issue] [title]", help="optional: the word issue, then the title")
    parser.add_argument("--title", help="issue title (emoji and tags allowed; it is normalized)")
    from common.paths import add_root_and_issue_args
    add_root_and_issue_args(parser, with_issue=False)


def _configure_normalize_title(parser) -> None:
    parser.add_argument("title", nargs="+")


def _configure_create_branch_name(parser) -> None:
    parser.add_argument("values", nargs="+", metavar="value",
                        help="<title> <number> or <owner> <repo> <title> <number>")
    parser.add_argument("--date", type=_date_arg, help="YYYYMMDD")


def _configure_get_commit_template(parser) -> None:
    parser.add_argument("issue_title")
    parser.add_argument("issue_url")
    # If omitted, derived from the title tag. Set it only when tag and content differ,
    # e.g. the issue is a feature but the actual work is a bug fix.
    parser.add_argument("--type", dest="commit_type", default=None, type=_commit_type_arg,
                       help="commit type (fix, docs, chore, ...). Default: inferred from the title tag")
    parser.add_argument("--scope", default=None, help="value for the {scope} placeholder")
    parser.add_argument("--repo-root", dest="repo_root", default=None,
                       help="repo root to read the format from (default: git root of the cwd, or the cwd outside git)")


COMMANDS = [
    Command(name="get-output-path", help="where to save the issue document (sequence number before the issue exists)", run=cmd_get_output_path,
            configure=_configure_get_output_path),
    Command(name="normalize-title", help="normalize a title", run=cmd_normalize_title,
            configure=_configure_normalize_title),
    Command(name="create-branch-name", help="build a branch name", run=cmd_create_branch_name,
            configure=_configure_create_branch_name),
    Command(name="get-commit-template", help="commit message template", run=cmd_get_commit_template,
            configure=_configure_get_commit_template),
]
