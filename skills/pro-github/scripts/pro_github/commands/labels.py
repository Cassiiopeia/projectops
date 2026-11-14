"""Label subcommands: list repo labels, add issue labels, remove one, replace all."""
from __future__ import annotations

from common.emit import emit
from common.gh_client import STATUS_LABEL_NAMES, GitHubAPIError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat, split_csv


def cmd_list_labels(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        labels = api.list_labels(args.owner, args.repo, pat)
        return emit({
            "count": len(labels),
            "labels": labels,
            "summary": f"{args.owner}/{args.repo}: {len(labels)} label(s)",
        })
    except GitHubAPIError as e:
        return api_error(e)


def cmd_add_labels(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    labels = split_csv(args.labels)
    try:
        applied = api.add_issue_labels(args.owner, args.repo, args.number, labels, pat)
        missing = [l for l in labels if l not in applied]
        out = {"labels": applied, "summary": f"#{args.number}: added labels (now {len(applied)})"}
        if missing:
            out["label_warning"] = f"labels ignored because the repo does not have them: {', '.join(missing)}"
        return emit(out)
    except GitHubAPIError as e:
        return api_error(e)


def cmd_remove_label(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        result = api.remove_issue_label(args.owner, args.repo, args.number, args.label, pat)
        return emit({**result, "summary": f"removed label '{args.label}' from #{args.number}"})
    except GitHubAPIError as e:
        # 404 if the issue never had the label — idempotent (already absent)
        if e.status_code == 404:
            return emit({
                "labels": None,
                "code": "label_not_present",
                "summary": f"#{args.number} already has no label '{args.label}' (no change)",
            })
        return api_error(e)


def cmd_set_labels(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    labels = split_csv(args.labels) if args.labels else []
    try:
        # Labels before replacing: read first so we can report what was removed
        before = api.get_issue_labels(args.owner, args.repo, args.number, pat)
        result = api.set_issue_labels(args.owner, args.repo, args.number, labels, pat)
        skipped = result.get("skipped", [])
        if result.get("unchanged"):
            # No label to apply, so the existing labels were left as is — reporting success would imply they were replaced
            return emit({
                "ok": False,
                "code": "no_valid_labels",
                "error": f"not replaced: none of the labels exist in the repo (existing labels kept): {', '.join(skipped)}",
                "labels": result["labels"],
                "label_warning": f"labels ignored because the repo does not have them: {', '.join(skipped)}",
                "next": f"list-labels {args.owner} {args.repo}",
            })
        removed = [label for label in before if label not in result["labels"]]
        out = {"labels": result["labels"], "removed": removed,
               "summary": f"#{args.number}: replaced all labels (now {len(result['labels'])}, removed {len(removed)})"}
        if skipped:
            out["label_warning"] = f"labels ignored because the repo does not have them: {', '.join(skipped)}"
        # Trying to change only the status label kept wiping type:·area: labels too
        removed_non_status = [label for label in removed if label not in STATUS_LABEL_NAMES]
        if removed_non_status:
            out["warning"] = f"non-status labels were removed too: {', '.join(removed_non_status)}"
            out["next"] = (f"if that was not intended, restore them with add-labels {args.owner} {args.repo} {args.number} "
                           f"\"{','.join(removed_non_status)}\". "
                           f"To change only the status, use finish-issue --outcome done|cancelled|in-progress")
        return emit(out)
    except GitHubAPIError as e:
        return api_error(e)


# ── Arguments ──

def _configure_list_labels(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")


def _configure_add_labels(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("labels", help="csv")


def _configure_remove_label(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("label")


def _configure_set_labels(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("labels", help="csv (empty removes all)", nargs="?", default="")


COMMANDS = [
    Command(name="list-labels", help="list repo labels", run=cmd_list_labels,
            configure=_configure_list_labels),
    Command(name="add-labels", help="add labels to an issue (keeps existing ones)", run=cmd_add_labels,
            configure=_configure_add_labels),
    Command(name="remove-label", help="remove one label from an issue", run=cmd_remove_label,
            configure=_configure_remove_label),
    Command(name="set-labels", help="replace all issue labels (also removes non-status labels; to finish an issue use finish-issue)", run=cmd_set_labels,
            configure=_configure_set_labels),
]
