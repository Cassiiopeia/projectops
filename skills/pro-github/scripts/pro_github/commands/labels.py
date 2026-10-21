"""라벨 서브커맨드: 레포 라벨 목록, 이슈 라벨 추가·하나 제거·전체 교체."""
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
        # 이슈에 그 라벨이 원래 없으면 404 — 멱등 처리 (이미 없는 상태)
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
        # 교체 전 라벨: 무엇이 지워졌는지 알리려면 먼저 읽어 둬야 한다
        before = api.get_issue_labels(args.owner, args.repo, args.number, pat)
        result = api.set_issue_labels(args.owner, args.repo, args.number, labels, pat)
        skipped = result.get("skipped", [])
        if result.get("unchanged"):
            # 적용할 라벨이 하나도 없어 기존 라벨을 그대로 둔 경우 — 성공으로 보고하면 교체된 줄 안다
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
        # 상태 라벨만 바꾸려다 type:·area: 라벨까지 지우는 사고가 반복됐다
        removed_non_status = [label for label in removed if label not in STATUS_LABEL_NAMES]
        if removed_non_status:
            out["warning"] = f"non-status labels were removed too: {', '.join(removed_non_status)}"
            out["next"] = (f"if that was not intended, restore them with add-labels {args.owner} {args.repo} {args.number} "
                           f"\"{','.join(removed_non_status)}\". "
                           f"To change only the status, use finish-issue --outcome done|cancelled|in-progress")
        return emit(out)
    except GitHubAPIError as e:
        return api_error(e)


# ── 인자 ──

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
