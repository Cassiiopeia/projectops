#!/usr/bin/env python3
"""github_cli — github skill 전용 CLI.

GitHub API 직접 호출 도구.
서브커맨드: get-issue, get-issues, update-issue, create-pr, list-prs,
           update-pr, search-issues, add-comment, explore, secrets

사용법:
    cd skills/pro-github/scripts
    python github_cli.py <subcommand> [args]

출력 형식: 모든 서브커맨드는 stdout으로 MCP-style JSON 출력.
    {"ok": true|false, "code": "...", "summary": "...", "next": "...", ...payload}
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Bootstrap — scripts/common import 가능하게 sys.path 조작 (cwd 무관 동작)
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402
from common.config import get_github_pat  # noqa: E402
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402
from common.gh_client import (  # noqa: E402
    GitHubAPIError, PyNaClMissingError,
    get_issue, get_issue_comments, update_issue, create_issue, list_issues,
    add_comment, update_comment, delete_comment,
    list_labels, add_issue_labels, remove_issue_label, set_issue_labels,
    add_assignees, remove_assignees,
    list_pulls, update_pull_request, create_pull_request,
    get_pull_detail, merge_pull_request,
    search_issues,
    get_user_type, list_repos, get_repo_detail, get_readme, get_languages, list_commits,
    upload_evidence_image, delete_release_asset, is_repo_private, EVIDENCE_TAG,
    list_secrets, set_secret,
    get_run, get_job_log, list_failed_runs, resolve_pr_runs, resolve_branch_runs,
)


# =========================================================================
# Subcommand handlers
# =========================================================================

def cmd_get_issue(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        issue = get_issue(args.owner, args.repo, args.number, pat)
        comments = get_issue_comments(args.owner, args.repo, args.number, pat) if args.with_comments else None
        return emit({
            "issue": issue,
            "comments": comments,
            "summary": f"#{issue['number']} {issue['state']} — {issue['title']}",
            "number": issue["number"],
            "title": issue["title"],
            "url": issue["url"],
            "html_url": issue["url"],
            "state": issue["state"],
            "body": issue.get("body", ""),
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_get_issues(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    issues = []
    for raw in args.numbers:
        try:
            number = int(raw)
        except ValueError:
            issues.append({"number": raw, "error": "정수 아님", "code": "invalid_argument"})
            continue
        try:
            issues.append(get_issue(args.owner, args.repo, number, pat))
        except GitHubAPIError as e:
            issues.append({"number": number, "error": str(e), "code": f"github_api_{e.status_code}"})
    return emit({
        "count": len(issues),
        "issues": issues,
        "summary": f"{len(issues)}개 이슈 조회 완료",
    })


def cmd_create_issue(args) -> int:
    # 입력을 자격증명보다 먼저 본다. 파일명 오타는 PAT 없이도 알려줄 수 있는데,
    # PAT 를 먼저 보면 "PAT 없음"만 나와 PAT 를 채운 뒤에야 오타를 알게 된다.
    body_path = Path(args.body_file)
    if not body_path.exists():
        return emit({
            "ok": False,
            "code": "body_file_not_found",
            "error": f"본문 파일이 존재하지 않습니다: {args.body_file}",
            "path_attempted": str(body_path.resolve()),
        })
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    body = body_path.read_text(encoding="utf-8")
    labels = [l.strip() for l in args.labels.split(",") if l.strip()] if args.labels else []
    assignees = [a.strip() for a in args.assignees.split(",") if a.strip()] if args.assignees else []
    try:
        result = create_issue(args.owner, args.repo, args.title, body, labels, pat, assignees)
        applied = result.get("assignees", [])
        missing = [a for a in assignees if a not in applied]
        out = {**result, "summary": f"이슈 #{result.get('number')} 생성 완료", "body_length": len(body)}
        if missing:
            out["assignee_warning"] = (
                f"담당자 지정 일부 실패: {', '.join(missing)} (레포 협업자/권한 확인 필요). 이슈는 정상 생성됨."
            )
        return emit(out)
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_list_issues(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        issues = list_issues(args.owner, args.repo, pat, state=args.state)
        # label/assignee 필터는 API 재호출 없이 여기서 후처리 (list_issues에 필드 있음)
        return emit({
            "count": len(issues),
            "issues": issues,
            "summary": f"{args.owner}/{args.repo} 이슈 {len(issues)}개 ({args.state})",
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_update_issue(args) -> int:
    # 입력 먼저, 자격증명 나중 (cmd_create_issue 와 같은 이유).
    body = None
    if args.body_file:
        body_path = Path(args.body_file)
        if not body_path.exists():
            return emit({
                "ok": False,
                "code": "body_file_not_found",
                "error": f"수정용 본문 파일이 존재하지 않습니다: {args.body_file}",
                "path_attempted": str(body_path.resolve())
            })
        body = body_path.read_text(encoding="utf-8")

    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    labels = [l.strip() for l in args.labels.split(",") if l.strip()] if args.labels else None
    assignees = [a.strip() for a in args.assignees.split(",") if a.strip()] if args.assignees else None

    try:
        result = update_issue(
            args.owner, args.repo, args.number, pat,
            title=args.title, body=body, state=args.state, labels=labels, assignees=assignees,
        )
        return emit({**result, "summary": f"#{args.number} 수정 완료"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_close_issue(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        result = update_issue(args.owner, args.repo, args.number, pat, state="closed")
        return emit({**result, "summary": f"#{args.number} 닫음"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_reopen_issue(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        result = update_issue(args.owner, args.repo, args.number, pat, state="open")
        return emit({**result, "summary": f"#{args.number} 다시 열음"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_add_comment(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    body_path = Path(args.body_file)
    if not body_path.exists():
        return emit({"ok": False, "code": "body_file_not_found", "error": f"{args.body_file} 없음"})
    body = body_path.read_text(encoding="utf-8")
    try:
        result = add_comment(args.owner, args.repo, args.number, body, pat)
        return emit({**result, "summary": f"#{args.number}에 댓글 추가 완료"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_list_comments(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        comments = get_issue_comments(args.owner, args.repo, args.number, pat)
        return emit({
            "count": len(comments),
            "comments": comments,
            "summary": f"#{args.number} 댓글 {len(comments)}개",
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_edit_comment(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    body_path = Path(args.body_file)
    if not body_path.exists():
        return emit({"ok": False, "code": "body_file_not_found", "error": f"{args.body_file} 없음"})
    body = body_path.read_text(encoding="utf-8")
    try:
        result = update_comment(args.owner, args.repo, args.comment_id, body, pat)
        return emit({**result, "summary": f"댓글 {args.comment_id} 수정 완료"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_delete_comment(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        result = delete_comment(args.owner, args.repo, args.comment_id, pat)
        return emit({**result, "summary": f"댓글 {args.comment_id} 삭제 완료"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_list_labels(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        labels = list_labels(args.owner, args.repo, pat)
        return emit({
            "count": len(labels),
            "labels": labels,
            "summary": f"{args.owner}/{args.repo} 라벨 {len(labels)}개",
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_add_labels(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    labels = [l.strip() for l in args.labels.split(",") if l.strip()]
    try:
        applied = add_issue_labels(args.owner, args.repo, args.number, labels, pat)
        missing = [l for l in labels if l not in applied]
        out = {"labels": applied, "summary": f"#{args.number} 라벨 추가 (현재 {len(applied)}개)"}
        if missing:
            out["label_warning"] = f"레포에 없어 무시된 라벨: {', '.join(missing)}"
        return emit(out)
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_remove_label(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        result = remove_issue_label(args.owner, args.repo, args.number, args.label, pat)
        return emit({**result, "summary": f"#{args.number}에서 라벨 '{args.label}' 제거"})
    except GitHubAPIError as e:
        # 이슈에 그 라벨이 원래 없으면 404 — 멱등 처리 (이미 없는 상태)
        if e.status_code == 404:
            return emit({
                "labels": None,
                "code": "label_not_present",
                "summary": f"#{args.number}에 라벨 '{args.label}'이(가) 이미 없음 (변경 없음)",
            })
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_set_labels(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    labels = [l.strip() for l in args.labels.split(",") if l.strip()] if args.labels else []
    try:
        result = set_issue_labels(args.owner, args.repo, args.number, labels, pat)
        return emit({**result, "summary": f"#{args.number} 라벨 전체 교체 (현재 {len(result['labels'])}개)"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_add_assignees(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    assignees = [a.strip() for a in args.assignees.split(",") if a.strip()]
    try:
        result = add_assignees(args.owner, args.repo, args.number, assignees, pat)
        applied = result.get("assignees", [])
        missing = [a for a in assignees if a not in applied]
        out = {**result, "summary": f"#{args.number} 담당자 추가 (현재 {len(applied)}명)"}
        if missing:
            out["assignee_warning"] = f"권한/협업자 아님으로 누락된 담당자: {', '.join(missing)}"
        return emit(out)
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_remove_assignees(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    assignees = [a.strip() for a in args.assignees.split(",") if a.strip()]
    try:
        result = remove_assignees(args.owner, args.repo, args.number, assignees, pat)
        return emit({**result, "summary": f"#{args.number} 담당자 제거 (현재 {len(result.get('assignees', []))}명)"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_create_pr(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    body_path = Path(args.body_file)
    body = body_path.read_text(encoding="utf-8") if body_path.exists() else ""
    try:
        result = create_pull_request(args.owner, args.repo, args.title, body, args.head, args.base, pat)
        return emit({
            **result,
            "summary": f"PR #{result.get('number')} 생성 완료",
            "next": f"list-prs {args.owner} {args.repo}",
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_list_prs(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        result = list_pulls(args.owner, args.repo, pat, args.state)
        return emit({
            "count": len(result),
            "prs": result,
            "summary": f"{args.owner}/{args.repo} PR {len(result)}개 ({args.state})",
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_update_pr(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    body = None
    if args.body_file:
        body_path = Path(args.body_file)
        body = body_path.read_text(encoding="utf-8") if body_path.exists() else None
    try:
        result = update_pull_request(
            args.owner, args.repo, args.number, pat,
            title=args.title, body=body, state=args.state,
        )
        return emit({**result, "summary": f"PR #{args.number} 수정 완료"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_get_pr(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        pr = get_pull_detail(args.owner, args.repo, args.number, pat)
        # mergeable_state가 아직 계산 전이면 unknown/None — agent가 재조회 판단
        state = pr.get("mergeable_state")
        if pr.get("merged"):
            verdict = "merged"
        elif pr.get("state") == "closed":
            verdict = "closed"
        elif state in (None, "unknown"):
            verdict = "computing"
        elif state in ("clean", "unstable", "has_hooks"):
            verdict = "mergeable"
        else:  # dirty, blocked, behind, draft
            verdict = "blocked"
        return emit({
            "pr": pr,
            "verdict": verdict,
            "summary": f"PR #{args.number} {pr.get('state')} / mergeable_state={state} → {verdict}",
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_add_pr_comment(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    body_path = Path(args.body_file)
    if not body_path.exists():
        return emit({"ok": False, "code": "body_file_not_found", "error": f"{args.body_file} 없음"})
    body = body_path.read_text(encoding="utf-8")
    try:
        # PR도 GitHub API에선 issue이므로 issues/{n}/comments로 댓글 추가
        result = add_comment(args.owner, args.repo, args.number, body, pat)
        return emit({**result, "summary": f"PR #{args.number}에 댓글 추가 완료"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_close_pr(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        result = update_pull_request(args.owner, args.repo, args.number, pat, state="closed")
        return emit({**result, "summary": f"PR #{args.number} 닫음"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_reopen_pr(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        result = update_pull_request(args.owner, args.repo, args.number, pat, state="open")
        return emit({**result, "summary": f"PR #{args.number} 다시 열음"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_merge_pr(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        result = merge_pull_request(
            args.owner, args.repo, args.number, pat,
            merge_method=args.method, commit_title=args.title, commit_message=args.message,
        )
        return emit({
            **result,
            "verdict": "merged" if result.get("merged") else "not_merged",
            "summary": f"PR #{args.number} 머지 완료 ({args.method})",
        })
    except GitHubAPIError as e:
        # 405: 머지 불가(충돌/체크 실패/드래프트), 409: sha 불일치, 422: rebase 불허
        verdict = {405: "not_mergeable", 409: "sha_mismatch", 422: "method_not_allowed"}.get(
            e.status_code, "error"
        )
        return emit({
            "ok": False,
            "code": f"github_api_{e.status_code}",
            "verdict": verdict,
            "error": str(e),
            "summary": f"PR #{args.number} 머지 실패: {verdict}",
        })


def cmd_search_issues(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    keyword = " ".join(args.keywords)
    try:
        result = search_issues(args.owner, args.repo, keyword, pat)
        return emit({
            "count": len(result),
            "items": result,
            "summary": f"\"{keyword}\" 검색 {len(result)}건",
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_normalize_title(args) -> int:
    from common.title import normalize
    result = normalize(" ".join(args.title))
    return emit({"normalized": result, "summary": result})


def cmd_create_branch_name(args) -> int:
    from common.gh_branch import create_branch_name
    name = create_branch_name(args.issue_title, args.issue_number, args.date)
    return emit({"branch": name, "summary": name})


def cmd_get_commit_template(args) -> int:
    from common.gh_branch import get_commit_template
    template = get_commit_template(args.issue_title, args.issue_url,
                                    getattr(args, "commit_type", None))
    return emit({"template": template, "summary": template})


def cmd_explore(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        if args.sub == "list-repos":
            owner_type = get_user_type(args.owner, pat) if args.type == "auto" else args.type
            repos = list_repos(args.owner, owner_type, pat)
            return emit({
                "owner": args.owner,
                "owner_type": owner_type,
                "count": len(repos),
                "repos": repos,
                "summary": f"{args.owner} {owner_type} 레포 {len(repos)}개",
                "next": f"explore repo-detail {args.owner} {repos[0]['name']}" if repos else None,
            })
        if not args.repo:
            return emit({"ok": False, "code": "missing_argument", "error": f"explore {args.sub}는 repo 인자 필요"})
        if args.sub == "repo-detail":
            detail = get_repo_detail(args.owner, args.repo, pat)
            return emit({
                "repo": detail,
                "summary": f"{args.owner}/{args.repo} 상세",
                "next": f"explore readme {args.owner} {args.repo}",
            })
        if args.sub == "readme":
            readme = get_readme(args.owner, args.repo, pat)
            return emit({
                "readme": readme,
                "summary": "README 조회",
                "next": f"explore languages {args.owner} {args.repo}",
            })
        if args.sub == "languages":
            langs = get_languages(args.owner, args.repo, pat)
            return emit({"languages": langs, "summary": f"언어 {len(langs)}개"})
        if args.sub == "commits":
            commits = list_commits(args.owner, args.repo, pat, limit=args.limit)
            return emit({
                "count": len(commits),
                "commits": commits,
                "summary": f"최근 커밋 {len(commits)}개",
            })
        return emit({"ok": False, "code": "unknown_subcommand", "error": f"알 수 없음: {args.sub}"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_upload_image(args) -> int:
    """이미지를 증적 릴리스에 올리고 바로 붙여넣을 마크다운까지 돌려준다.

    GitHub 공식 첨부 업로드는 브라우저 세션이 필요해 PAT로 쓸 수 없다. 릴리스 자산이
    유일하게 PAT로 가능한 경로이고, 실측으로 이슈 본문·댓글 양쪽에서 <img>로 렌더링되는
    것을 확인했다 (자세한 근거는 gh_client의 주석).
    """
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    # 파일 확인이 먼저다. 네트워크를 먼저 치면 "파일이 없다"가 "레포가 없다"(404)로
    # 둔갑해 원인을 못 짚는다. 올릴 것이 하나도 없으면 API를 부를 이유도 없다.
    missing = [f for f in args.files if not Path(f).expanduser().is_file()]
    if len(missing) == len(args.files):
        return emit({
            "ok": False, "code": "no_image_uploaded",
            "error": "올릴 파일이 없습니다",
            "failed": [{"file": f, "error": "파일이 없습니다"} for f in missing],
        })

    try:
        # private이면 익명 접근이 막혀 이미지가 깨진다. 올리기 전에 알린다 —
        # 올리고 나서 알면 이미 이슈에 깨진 이미지가 박힌 뒤다.
        warning = None
        if is_repo_private(args.owner, args.repo, pat):
            warning = ("private 레포라 이미지가 렌더링되지 않습니다(익명 접근 차단). "
                       "URL은 발급되지만 이슈에서는 깨져 보입니다.")

        images, failed = [], []
        for f in args.files:
            try:
                images.append(upload_evidence_image(
                    args.owner, args.repo, f, pat, tag=args.tag, prefix=args.prefix))
            except FileNotFoundError as e:
                failed.append({"file": f, "error": str(e)})

        if not images:
            return emit({"ok": False, "code": "no_image_uploaded",
                         "error": "올린 이미지가 없습니다", "failed": failed})

        return emit({
            "count": len(images),
            "images": images,
            # 그대로 본문·댓글 파일에 붙여넣을 수 있게 합쳐서 준다
            "markdown": "\n".join(i["markdown"] for i in images),
            "failed": failed or None,
            "private_warning": warning,
            "summary": f"이미지 {len(images)}개 업로드 완료",
            "next": f"add-comment {args.owner} {args.repo} <이슈번호> <본문파일>",
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_delete_image(args) -> int:
    """올린 증적을 지운다. 검증용으로 올린 것을 치울 때 쓴다."""
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        delete_release_asset(args.owner, args.repo, int(args.asset_id), pat)
        return emit({"asset_id": int(args.asset_id), "status": "deleted",
                     "summary": f"증적 {args.asset_id} 삭제 완료"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_secrets(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        if args.sub == "list":
            secrets = list_secrets(args.owner, args.repo, pat)
            return emit({
                "count": len(secrets),
                "secrets": secrets,
                "summary": f"{args.owner}/{args.repo} secret {len(secrets)}개",
            })
        if args.sub == "set":
            if not args.name:
                return emit({"ok": False, "code": "missing_argument", "error": "name 필요"})
            value = os.environ.get("SECRET_VALUE")
            if value is None:
                return emit({
                    "ok": False, "code": "missing_secret_value",
                    "error": "SECRET_VALUE 환경변수에 값을 담아 호출하세요.",
                })
            result = set_secret(args.owner, args.repo, args.name, value, pat)
            return emit({**result, "summary": f"secret {args.name} 갱신 완료"})
        return emit({"ok": False, "code": "unknown_subcommand", "error": f"알 수 없음: {args.sub}"})
    except PyNaClMissingError as e:
        return emit({"ok": False, "code": e.code, "error": str(e), "hint": "pip install PyNaCl"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def _actions_int(args, name: str):
    """위치 인자를 숫자로 읽는다. 없거나 숫자가 아니면 그 사실을 말해 준다.

    파서에서 `type=int` 로 걸면 argparse 가 무엇이 잘못됐는지 못 알려준 채
    죽는다 (#622 에서 `invalid int value: 'develop'` 이 그랬다).
    """
    raw = args.arg
    if raw is None:
        return None, emit({"ok": False, "code": "missing_argument",
                           "error": f"{name} 필요",
                           "hint": f"actions {args.sub} {args.owner} {args.repo} <{name}>"})
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, emit({"ok": False, "code": "bad_argument",
                           "error": f"{name} 는 숫자여야 합니다: {raw!r}",
                           "hint": f"actions {args.sub} {args.owner} {args.repo} <{name}>"})


def cmd_actions(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        if args.sub == "show-run":
            run_id, err = _actions_int(args, "run_id")
            if err is not None:
                return err
            result = get_run(args.owner, args.repo, run_id, pat)
            return emit({
                **result,
                "summary": f"Run {run_id} 상태: {result.get('status')} / {result.get('conclusion')}",
                "next": f"actions joblog {args.owner} {args.repo} {result['failed_job_ids'][0]}" if result.get("failed_job_ids") else None
            })
        elif args.sub == "joblog":
            job_id, err = _actions_int(args, "job_id")
            if err is not None:
                return err
            result = get_job_log(args.owner, args.repo, job_id, pat, grep=args.grep, tail=args.tail)
            return emit({
                **result,
                "summary": f"Job {job_id} 로그 {result.get('matched_count')}건 검색됨"
            })
        elif args.sub == "list-failed":
            result = list_failed_runs(args.owner, args.repo, pat, limit=args.limit)
            return emit({
                "runs": result,
                "count": len(result),
                "summary": f"최근 실패한 run {len(result)}개"
            })
        elif args.sub == "resolve-pr":
            pr_number, err = _actions_int(args, "pr_number")
            if err is not None:
                return err
            result = resolve_pr_runs(args.owner, args.repo, pr_number, pat)
            return emit({
                **result,
                "summary": f"PR #{pr_number}에 연결된 run {len(result.get('runs', []))}개 조회됨",
                "next": f"actions show-run {args.owner} {args.repo} {result['runs'][0]['run_id']}" if result.get("runs") else None
            })
        elif args.sub == "resolve-branch":
            if not args.arg:
                return emit({"ok": False, "code": "missing_argument", "error": "branch 필요",
                             "hint": f"actions resolve-branch {args.owner} {args.repo} <branch>"})
            result = resolve_branch_runs(args.owner, args.repo, args.arg, pat, limit=args.limit)
            return emit({
                "runs": result,
                "count": len(result),
                "summary": f"브랜치 {args.arg}의 run {len(result)}개",
                "next": f"actions show-run {args.owner} {args.repo} {result[0]['run_id']}" if result else None
            })
        return emit({"ok": False, "code": "unknown_subcommand", "error": f"알 수 없음: {args.sub}"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


# =========================================================================
# argparse setup
# =========================================================================

def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(
        prog="github_cli",
        description="github skill 전용 GitHub API CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_gi = sub.add_parser("get-issue", help="이슈 조회")
    p_gi.add_argument("owner")
    p_gi.add_argument("repo")
    p_gi.add_argument("number", type=int)
    p_gi.add_argument("--with-comments", action="store_true")
    p_gi.set_defaults(func=cmd_get_issue)

    p_gis = sub.add_parser("get-issues", help="여러 이슈 한 번에 조회")
    p_gis.add_argument("owner")
    p_gis.add_argument("repo")
    p_gis.add_argument("numbers", nargs="+")
    p_gis.set_defaults(func=cmd_get_issues)

    p_cri = sub.add_parser("create-issue", help="이슈 생성")
    p_cri.add_argument("owner")
    p_cri.add_argument("repo")
    p_cri.add_argument("title")
    p_cri.add_argument("body_file")
    p_cri.add_argument("labels", help="csv")
    p_cri.add_argument("--assignees", help="담당자 csv")
    p_cri.set_defaults(func=cmd_create_issue)

    p_lis = sub.add_parser("list-issues", help="이슈 목록")
    p_lis.add_argument("owner")
    p_lis.add_argument("repo")
    p_lis.add_argument("--state", choices=["open", "closed", "all"], default="open")
    p_lis.set_defaults(func=cmd_list_issues)

    p_ui = sub.add_parser("update-issue", help="이슈 수정")
    p_ui.add_argument("owner")
    p_ui.add_argument("repo")
    p_ui.add_argument("number", type=int)
    p_ui.add_argument("--title")
    p_ui.add_argument("--state", choices=["open", "closed"])
    p_ui.add_argument("--labels", help="csv")
    p_ui.add_argument("--assignees", help="csv")
    p_ui.add_argument("--body-file", help="본문 파일 경로")
    p_ui.set_defaults(func=cmd_update_issue)

    p_cli = sub.add_parser("close-issue", help="이슈 닫기")
    p_cli.add_argument("owner")
    p_cli.add_argument("repo")
    p_cli.add_argument("number", type=int)
    p_cli.set_defaults(func=cmd_close_issue)

    p_roi = sub.add_parser("reopen-issue", help="이슈 다시 열기")
    p_roi.add_argument("owner")
    p_roi.add_argument("repo")
    p_roi.add_argument("number", type=int)
    p_roi.set_defaults(func=cmd_reopen_issue)

    p_ac = sub.add_parser("add-comment", help="이슈 댓글 추가")
    p_ac.add_argument("owner")
    p_ac.add_argument("repo")
    p_ac.add_argument("number", type=int)
    p_ac.add_argument("body_file")
    p_ac.set_defaults(func=cmd_add_comment)

    p_lc = sub.add_parser("list-comments", help="이슈/PR 댓글 목록")
    p_lc.add_argument("owner")
    p_lc.add_argument("repo")
    p_lc.add_argument("number", type=int)
    p_lc.set_defaults(func=cmd_list_comments)

    p_ec = sub.add_parser("edit-comment", help="댓글 수정")
    p_ec.add_argument("owner")
    p_ec.add_argument("repo")
    p_ec.add_argument("comment_id", type=int)
    p_ec.add_argument("body_file")
    p_ec.set_defaults(func=cmd_edit_comment)

    p_dc = sub.add_parser("delete-comment", help="댓글 삭제")
    p_dc.add_argument("owner")
    p_dc.add_argument("repo")
    p_dc.add_argument("comment_id", type=int)
    p_dc.set_defaults(func=cmd_delete_comment)

    p_ll = sub.add_parser("list-labels", help="레포 라벨 목록")
    p_ll.add_argument("owner")
    p_ll.add_argument("repo")
    p_ll.set_defaults(func=cmd_list_labels)

    p_al = sub.add_parser("add-labels", help="이슈에 라벨 추가 (기존 유지)")
    p_al.add_argument("owner")
    p_al.add_argument("repo")
    p_al.add_argument("number", type=int)
    p_al.add_argument("labels", help="csv")
    p_al.set_defaults(func=cmd_add_labels)

    p_rl = sub.add_parser("remove-label", help="이슈에서 라벨 하나 제거")
    p_rl.add_argument("owner")
    p_rl.add_argument("repo")
    p_rl.add_argument("number", type=int)
    p_rl.add_argument("label")
    p_rl.set_defaults(func=cmd_remove_label)

    p_sl = sub.add_parser("set-labels", help="이슈 라벨 전체 교체")
    p_sl.add_argument("owner")
    p_sl.add_argument("repo")
    p_sl.add_argument("number", type=int)
    p_sl.add_argument("labels", help="csv (빈 값이면 전부 제거)", nargs="?", default="")
    p_sl.set_defaults(func=cmd_set_labels)

    p_aa = sub.add_parser("add-assignees", help="이슈 담당자 추가 (기존 유지)")
    p_aa.add_argument("owner")
    p_aa.add_argument("repo")
    p_aa.add_argument("number", type=int)
    p_aa.add_argument("assignees", help="csv")
    p_aa.set_defaults(func=cmd_add_assignees)

    p_ra = sub.add_parser("remove-assignees", help="이슈 담당자 일부 제거")
    p_ra.add_argument("owner")
    p_ra.add_argument("repo")
    p_ra.add_argument("number", type=int)
    p_ra.add_argument("assignees", help="csv")
    p_ra.set_defaults(func=cmd_remove_assignees)

    p_cp = sub.add_parser("create-pr", help="PR 생성")
    p_cp.add_argument("owner")
    p_cp.add_argument("repo")
    p_cp.add_argument("title")
    p_cp.add_argument("body_file")
    p_cp.add_argument("head")
    p_cp.add_argument("base")
    p_cp.set_defaults(func=cmd_create_pr)

    p_lp = sub.add_parser("list-prs", help="PR 목록")
    p_lp.add_argument("owner")
    p_lp.add_argument("repo")
    p_lp.add_argument("--state", choices=["open", "closed", "all"], default="open")
    p_lp.set_defaults(func=cmd_list_prs)

    p_up = sub.add_parser("update-pr", help="PR 수정")
    p_up.add_argument("owner")
    p_up.add_argument("repo")
    p_up.add_argument("number", type=int)
    p_up.add_argument("body_file", nargs="?")
    p_up.add_argument("--title")
    p_up.add_argument("--state", choices=["open", "closed"])
    p_up.set_defaults(func=cmd_update_pr)

    p_gpr = sub.add_parser("get-pr", help="PR 상세 (mergeable_state 등)")
    p_gpr.add_argument("owner")
    p_gpr.add_argument("repo")
    p_gpr.add_argument("number", type=int)
    p_gpr.set_defaults(func=cmd_get_pr)

    p_apc = sub.add_parser("add-pr-comment", help="PR에 댓글 추가")
    p_apc.add_argument("owner")
    p_apc.add_argument("repo")
    p_apc.add_argument("number", type=int)
    p_apc.add_argument("body_file")
    p_apc.set_defaults(func=cmd_add_pr_comment)

    p_clp = sub.add_parser("close-pr", help="PR 닫기")
    p_clp.add_argument("owner")
    p_clp.add_argument("repo")
    p_clp.add_argument("number", type=int)
    p_clp.set_defaults(func=cmd_close_pr)

    p_rop = sub.add_parser("reopen-pr", help="PR 다시 열기")
    p_rop.add_argument("owner")
    p_rop.add_argument("repo")
    p_rop.add_argument("number", type=int)
    p_rop.set_defaults(func=cmd_reopen_pr)

    p_mp = sub.add_parser("merge-pr", help="PR 머지")
    p_mp.add_argument("owner")
    p_mp.add_argument("repo")
    p_mp.add_argument("number", type=int)
    p_mp.add_argument("--method", choices=["merge", "squash", "rebase"], default="merge")
    p_mp.add_argument("--title", help="머지 커밋 제목")
    p_mp.add_argument("--message", help="머지 커밋 본문")
    p_mp.set_defaults(func=cmd_merge_pr)

    p_si = sub.add_parser("search-issues", help="이슈 검색")
    p_si.add_argument("owner")
    p_si.add_argument("repo")
    p_si.add_argument("keywords", nargs="+")
    p_si.set_defaults(func=cmd_search_issues)

    p_nt = sub.add_parser("normalize-title", help="제목 정규화")
    p_nt.add_argument("title", nargs="+")
    p_nt.set_defaults(func=cmd_normalize_title)

    p_cbn = sub.add_parser("create-branch-name", help="브랜치명 생성")
    p_cbn.add_argument("issue_title")
    p_cbn.add_argument("issue_number", type=int)
    p_cbn.add_argument("--date", help="YYYYMMDD")
    p_cbn.set_defaults(func=cmd_create_branch_name)

    p_gct = sub.add_parser("get-commit-template", help="커밋 메시지 템플릿")
    p_gct.add_argument("issue_title")
    p_gct.add_argument("issue_url")
    # 생략하면 제목 태그에서 유도한다. 이슈는 기능인데 실제 작업이 버그 수정인
    # 경우처럼 태그와 내용이 다를 때만 직접 지정한다.
    p_gct.add_argument("--type", dest="commit_type", default=None,
                       help="커밋 타입 (fix·docs·chore 등). 생략하면 제목 태그에서 유도")
    p_gct.set_defaults(func=cmd_get_commit_template)

    p_ex = sub.add_parser("explore", help="레포 탐색 (list-repos|repo-detail|readme|languages|commits)")
    p_ex.add_argument("sub", choices=["list-repos", "repo-detail", "readme", "languages", "commits"])
    p_ex.add_argument("owner")
    p_ex.add_argument("repo", nargs="?")
    p_ex.add_argument("--type", choices=["user", "org", "auto"], default="auto")
    p_ex.add_argument("--limit", type=int, default=10)
    p_ex.set_defaults(func=cmd_explore)

    p_ui = sub.add_parser("upload-image", help="이미지를 증적 릴리스에 올려 마크다운을 받는다")
    p_ui.add_argument("owner")
    p_ui.add_argument("repo")
    p_ui.add_argument("files", nargs="+", help="이미지 파일 경로 (여러 개 가능)")
    p_ui.add_argument("--tag", default=EVIDENCE_TAG, help=f"증적 릴리스 태그 (기본 {EVIDENCE_TAG})")
    p_ui.add_argument("--prefix", default=None, help="자산 이름 앞에 붙일 말 (예: issue585)")
    p_ui.set_defaults(func=cmd_upload_image)

    p_di = sub.add_parser("delete-image", help="올린 증적 이미지를 지운다")
    p_di.add_argument("owner")
    p_di.add_argument("repo")
    p_di.add_argument("asset_id")
    p_di.set_defaults(func=cmd_delete_image)

    p_sc = sub.add_parser("secrets", help="Actions Secret 관리 (list|set)")
    p_sc.add_argument("sub", choices=["list", "set"])
    p_sc.add_argument("owner")
    p_sc.add_argument("repo")
    p_sc.add_argument("name", nargs="?")
    p_sc.set_defaults(func=cmd_secrets)

    p_ac = sub.add_parser("actions", help="GitHub Actions 로그 관리")
    p_ac.add_argument("sub", choices=["show-run", "joblog", "list-failed", "resolve-pr", "resolve-branch"])
    p_ac.add_argument("owner")
    p_ac.add_argument("repo")
    # ⚠️ 위치 인자는 **하나**여야 한다 (#622). 예전에는 run_id·job_id·pr_number·
    # branch 를 줄줄이 선택 인자로 뒀는데, argparse 는 값을 **왼쪽부터** 채우므로
    # 어떤 서브커맨드를 부르든 첫 값이 run_id 로 들어갔다. joblog·resolve-pr·
    # resolve-branch 셋이 문서에 적힌 그대로 불러도 깨졌고, show-run 과
    # list-failed 만 우연히 맞았다. 형제인 changelog_cli 는 처음부터 하나였다.
    p_ac.add_argument("arg", nargs="?",
                      help="서브커맨드에 따라 run_id · job_id · pr_number · branch")
    p_ac.add_argument("--grep", default="error", help="Filter logs")
    p_ac.add_argument("--tail", type=int, default=30, help="Log line count")
    p_ac.add_argument("--limit", type=int, default=10, help="Run count limit")
    p_ac.set_defaults(func=cmd_actions)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
