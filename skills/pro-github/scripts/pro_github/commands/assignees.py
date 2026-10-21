"""담당자 서브커맨드: 추가(기존 유지)·일부 제거."""
from __future__ import annotations

from common.emit import emit
from common.gh_client import GitHubAPIError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat, split_csv


def cmd_add_assignees(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    assignees = split_csv(args.assignees)
    try:
        result = api.add_assignees(args.owner, args.repo, args.number, assignees, pat)
        applied = result.get("assignees", [])
        missing = [a for a in assignees if a not in applied]
        out = {**result, "summary": f"#{args.number}: added assignees (now {len(applied)})"}
        if missing:
            out["assignee_warning"] = f"assignees skipped (no permission or not a collaborator): {', '.join(missing)}"
        return emit(out)
    except GitHubAPIError as e:
        return api_error(e)


def cmd_remove_assignees(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    assignees = split_csv(args.assignees)
    try:
        result = api.remove_assignees(args.owner, args.repo, args.number, assignees, pat)
        return emit({**result, "summary": f"#{args.number}: removed assignees (now {len(result.get('assignees', []))})"})
    except GitHubAPIError as e:
        return api_error(e)


# ── 인자 ──

def _configure_add_assignees(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("assignees", help="csv")


def _configure_remove_assignees(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("assignees", help="csv")


COMMANDS = [
    Command(name="add-assignees", help="add issue assignees (keeps existing ones)", run=cmd_add_assignees,
            configure=_configure_add_assignees),
    Command(name="remove-assignees", help="remove some issue assignees", run=cmd_remove_assignees,
            configure=_configure_remove_assignees),
]
