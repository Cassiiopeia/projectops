"""finish-issue: 상태 라벨 교체 + 닫기를 한 명령으로. 중간에 실패해도 어디까지 됐는지 알려 준다 (#941)."""
from __future__ import annotations

from common.emit import emit
from common.gh_client import GitHubAPIError
from common.github_rest.labels import LABEL_ALIAS_GROUPS
from pro_github.registry import Command
from pro_github.responses import missing_pat

# 상태 라벨 이름 전부 (한글·영문): 교체할 때 이것만 걷어 내고 나머지 라벨은 지킨다
_STATUS_LABEL_NAMES = {name for group in LABEL_ALIAS_GROUPS[:7] for name in group}

# 결과별: (붙일 상태 라벨, 닫을 때 사유 | None=닫지 않음)
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

    # 상태 라벨 교체 (상태 외 라벨은 유지)
    wanted = [label for label in current if label not in _STATUS_LABEL_NAMES] + [status_label]
    try:
        replaced = api.set_issue_labels(args.owner, args.repo, args.number, wanted, pat)
        if replaced.get("unchanged"):
            steps.append({"step": "labels", "ok": False, "code": "no_valid_labels",
                          "detail": f"레포에 상태 라벨이 없어 교체하지 못했다: {status_label}"})
        else:
            steps.append({"step": "labels", "ok": True, "labels": replaced.get("labels")})
    except GitHubAPIError as e:
        steps.append({"step": "labels", "ok": False, "code": f"github_api_{e.status_code}", "detail": str(e)})

    # 닫기 (라벨 단계가 실패해도 시도한다: 닫힌 이슈에 상태 라벨이 없는 것이 라벨만 바뀐 열린 이슈보다 낫다)
    if close_reason:
        try:
            api.update_issue(args.owner, args.repo, args.number, pat, state="closed", state_reason=close_reason)
            steps.append({"step": "close", "ok": True, "reason": close_reason})
        except GitHubAPIError as e:
            steps.append({"step": "close", "ok": False, "code": f"github_api_{e.status_code}", "detail": str(e)})

    failed = [step["step"] for step in steps if not step["ok"]]
    return emit({
        "ok": not failed,
        "code": "finished" if not failed else "finished_partial",
        "steps": steps,
        "failed_steps": failed,
        "summary": (f"#{args.number} 완료 처리: " + " > ".join(f"{s['step']} {'ok' if s['ok'] else '실패'}" for s in steps)),
        "next": None if not failed else f"실패한 단계만 다시: {', '.join(failed)} (set-labels / close-issue)",
    })


def _configure_finish_issue(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("number", type=int)
    parser.add_argument("--outcome", choices=sorted(_OUTCOMES), default="done",
                        help="done: status: done + 닫기 / cancelled: status: cancelled + 닫기 / in-progress: 라벨만")


COMMANDS = [
    Command(name="finish-issue", help="상태 라벨 교체 + 닫기를 한 번에 (부분 성공을 단계별로 보고)",
            run=cmd_finish_issue, configure=_configure_finish_issue),
]
