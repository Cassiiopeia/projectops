"""라벨 서브커맨드: 레포 라벨 목록, 이슈 라벨 추가·하나 제거·전체 교체."""
from __future__ import annotations

from common.emit import emit
from common.gh_client import GitHubAPIError
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
            "summary": f"{args.owner}/{args.repo} 라벨 {len(labels)}개",
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
        out = {"labels": applied, "summary": f"#{args.number} 라벨 추가 (현재 {len(applied)}개)"}
        if missing:
            out["label_warning"] = f"레포에 없어 무시된 라벨: {', '.join(missing)}"
        return emit(out)
    except GitHubAPIError as e:
        return api_error(e)


def cmd_remove_label(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        result = api.remove_issue_label(args.owner, args.repo, args.number, args.label, pat)
        return emit({**result, "summary": f"#{args.number}에서 라벨 '{args.label}' 제거"})
    except GitHubAPIError as e:
        # 이슈에 그 라벨이 원래 없으면 404 — 멱등 처리 (이미 없는 상태)
        if e.status_code == 404:
            return emit({
                "labels": None,
                "code": "label_not_present",
                "summary": f"#{args.number}에 라벨 '{args.label}'이(가) 이미 없음 (변경 없음)",
            })
        return api_error(e)


def cmd_set_labels(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    labels = split_csv(args.labels) if args.labels else []
    try:
        result = api.set_issue_labels(args.owner, args.repo, args.number, labels, pat)
        skipped = result.get("skipped", [])
        if result.get("unchanged"):
            # 적용할 라벨이 하나도 없어 기존 라벨을 그대로 둔 경우 — 성공으로 보고하면 교체된 줄 안다
            return emit({
                "ok": False,
                "code": "no_valid_labels",
                "error": f"레포에 없는 라벨뿐이라 교체하지 않았습니다 (기존 라벨 유지): {', '.join(skipped)}",
                "labels": result["labels"],
                "label_warning": f"레포에 없어 무시된 라벨: {', '.join(skipped)}",
                "next": f"list-labels {args.owner} {args.repo}",
            })
        out = {"labels": result["labels"],
               "summary": f"#{args.number} 라벨 전체 교체 (현재 {len(result['labels'])}개)"}
        if skipped:
            out["label_warning"] = f"레포에 없어 무시된 라벨: {', '.join(skipped)}"
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
    parser.add_argument("labels", help="csv (빈 값이면 전부 제거)", nargs="?", default="")


COMMANDS = [
    Command(name="list-labels", help="레포 라벨 목록", run=cmd_list_labels,
            configure=_configure_list_labels),
    Command(name="add-labels", help="이슈에 라벨 추가 (기존 유지)", run=cmd_add_labels,
            configure=_configure_add_labels),
    Command(name="remove-label", help="이슈에서 라벨 하나 제거", run=cmd_remove_label,
            configure=_configure_remove_label),
    Command(name="set-labels", help="이슈 라벨 전체 교체", run=cmd_set_labels,
            configure=_configure_set_labels),
]
