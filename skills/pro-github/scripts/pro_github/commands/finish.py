"""finish-issue: 상태 라벨 교체 + 닫기를 한 명령으로. 중간에 실패해도 어디까지 됐는지 알려 준다 (#941)."""
from __future__ import annotations

import urllib.error

from common.emit import emit
from common.gh_client import STATUS_LABEL_NAMES, GitHubAPIError
from common.report_comment import REPORT_COMMENT_MARKER
from pro_github.registry import Command
from pro_github.responses import missing_pat

# 표식 없는 옛 보고서 댓글 판별: 출력 틀의 고정 제목 2개 (휴리스틱)
_REPORT_TEMPLATE_HEADINGS = ("## 개요", "## 변경 사항")

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
    wanted = [label for label in current if label not in STATUS_LABEL_NAMES] + [status_label]
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
    # 보고서 없이 닫는 일이 반복됐다 (40개 일괄 종료) — 막지는 않고 알린다
    warnings = _report_warnings(args, api, pat) if args.outcome == "done" else []
    return emit({
        "ok": not failed,
        "code": "finished" if not failed else "finished_partial",
        "steps": steps,
        "failed_steps": failed,
        "warnings": warnings,
        "summary": (f"#{args.number} 완료 처리: " + " > ".join(f"{s['step']} {'ok' if s['ok'] else '실패'}" for s in steps)),
        "next": (f"실패한 단계만 다시: {', '.join(failed)} (finish-issue 재실행 또는 close-issue)" if failed
                 else "보고서가 빠졌다면 pro-report 로 작성해 이 이슈에 댓글로 남긴다" if warnings else None),
    })


def is_report_comment(body: str) -> bool:
    """pro-report 보고서 댓글인지: 표식 또는 출력 틀 제목(## 개요 · ## 변경 사항)이 모두 있음"""
    body = body or ""
    return REPORT_COMMENT_MARKER in body or all(heading in body for heading in _REPORT_TEMPLATE_HEADINGS)


def _report_warnings(args, api, pat: str) -> list[str]:
    """보고서 댓글이 없으면 경고 1줄. 댓글 조회 실패도 경고로 남긴다 (완료 처리는 그대로)"""
    try:
        comments = api.get_issue_comments(args.owner, args.repo, args.number, pat)
    except (GitHubAPIError, urllib.error.URLError, TimeoutError, ConnectionError) as error:
        return [f"보고서 댓글 확인 실패: {error}"]
    if any(is_report_comment(comment.get("body", "")) for comment in comments):
        return []
    return [f"#{args.number} 에 보고서 댓글이 없다 (판별: 표식 {REPORT_COMMENT_MARKER} 또는 '## 개요'+'## 변경 사항' 제목). "
            f"pro-report 로 보고서를 남겼는지 확인한다"]


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
