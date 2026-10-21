"""GitHub Actions: run 상세·job 로그·실패 run·PR/브랜치별 run."""

from __future__ import annotations

import re
import time
import urllib.parse

from common import gh_client as client
from common.github_rest.transport import _API_BASE


def _run_summary(run: dict) -> dict:
    """workflow run 객체에서 요약 필드만 추출한다."""
    return {
        "run_id": run["id"],
        "name": run.get("name"),
        "path": run.get("path"),
        "branch": run.get("head_branch"),
        "event": run.get("event"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "created_at": (run.get("created_at") or "")[:16],
        "url": run.get("html_url"),
    }


def get_run(owner: str, repo: str, run_id: int, pat: str) -> dict:
    """단일 run 메타 + job 목록(실패 step 포함)을 반환한다."""
    run = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}", None, pat)
    result = client._run_summary(run)
    jobs_data = client._request(
        "GET", f"{_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs?per_page=100", None, pat
    )
    jobs = []
    failed_job_ids = []
    for j in jobs_data.get("jobs", []):
        failed_steps = [
            s["name"] for s in (j.get("steps") or []) if s.get("conclusion") == "failure"
        ]
        jobs.append({
            "job_id": j["id"],
            "name": j["name"],
            "conclusion": j.get("conclusion"),
            "failed_steps": failed_steps,
        })
        if j.get("conclusion") == "failure":
            failed_job_ids.append(j["id"])
    result["jobs"] = jobs
    result["failed_job_ids"] = failed_job_ids
    return result


# 기본 로그 검색: 실패 표시 줄 (GitHub 이 실패 step 에 남기는 표식)
ERROR_MARKER = "##[error]"
# ##[error] 줄 앞에 함께 보여 줄 출력 줄 수 (실패 step 주변)
_ERROR_CONTEXT_LINES = 8
# ##[error] 가 없을 때 기본 검색
_FALLBACK_PATTERN = "error|failed"


def get_job_log(
    owner: str, repo: str, job_id: int, pat: str,
    grep: str | None = None, tail: int = 30, save_to: str | None = None,
) -> dict:
    """job 로그를 받아 grep 매칭 라인의 끝 tail개를 반환한다.

    grep 없음(기본): ##[error] 줄과 그 앞 출력 줄. `##[group]Run` 스크립트 원문 구간은 빼고 본다
    (원문의 `error` 글자·브랜치명이 걸리지 않게). grep 지정: 정규식으로 전체 줄 검색.
    job logs 엔드포인트는 Azure로 redirect되므로 _request의 strip 핸들러가 필수.
    """
    text = client._request(
        "GET", f"{_API_BASE}/repos/{owner}/{repo}/actions/jobs/{job_id}/logs", None, pat, raw=True
    )
    all_lines = text.splitlines()
    if grep is None:
        matched, mode, is_regex = _error_marker_lines(all_lines), "error_markers", False
    else:
        matches_line, is_regex = _line_matcher(grep)
        matched, mode = [l for l in all_lines if matches_line(l)], "grep"
    result = {
        "job_id": job_id,
        "total_lines": len(all_lines),
        "matched_count": len(matched),
        "grep": grep,
        "mode": mode,
        "regex": is_regex,
        "lines": [l[:300] for l in matched[-tail:]],
    }
    if save_to:
        # 전체 로그는 파일로: 응답에 다 싣지 않아도 나중에 직접 grep 할 수 있다 (#939)
        from pathlib import Path
        Path(save_to).write_text(text, encoding="utf-8")
        result["saved_to"] = save_to
    return result


def _output_line_indexes(lines: list[str]) -> list[int]:
    """`##[group]Run …` ~ `##[endgroup]` (실행 스크립트 원문) 밖의 줄 번호"""
    indexes, is_inside_run_source = [], False
    for index, line in enumerate(lines):
        if "##[group]Run " in line:
            is_inside_run_source = True
            continue
        if is_inside_run_source:
            if "##[endgroup]" in line:
                is_inside_run_source = False
            continue
        indexes.append(index)
    return indexes


def _error_marker_lines(lines: list[str]) -> list[str]:
    """##[error] 줄 + 그 앞 출력 줄 (스크립트 원문 제외). ##[error] 가 없으면 error|failed 로 대신 찾는다"""
    output_indexes = _output_line_indexes(lines)
    marker_positions = [position for position, index in enumerate(output_indexes) if ERROR_MARKER in lines[index]]
    if not marker_positions:
        matches_line, _ = _line_matcher(_FALLBACK_PATTERN)
        return [lines[index] for index in output_indexes if matches_line(lines[index])]
    picked: list[int] = []
    for position in marker_positions:
        for neighbor in output_indexes[max(0, position - _ERROR_CONTEXT_LINES):position + 1]:
            if neighbor not in picked:
                picked.append(neighbor)
    return [lines[index] for index in sorted(picked)]


def _line_matcher(grep: str):
    """(줄 판정 함수, 정규식으로 해석했는지). 대소문자 무시, `a|b` 같은 정규식을 받고 틀린 정규식은 글자 그대로 찾는다 (#939)"""
    try:
        pattern = re.compile(grep, re.IGNORECASE)
        return (lambda line: pattern.search(line) is not None), True
    except re.error:
        needle = grep.lower()
        return (lambda line: needle in line.lower()), False


def list_failed_runs(owner: str, repo: str, pat: str, limit: int = 10) -> list[dict]:
    """최근 실패(conclusion=failure) run 목록을 반환한다."""
    data = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/actions/runs?status=failure&per_page={limit}",
        None, pat,
    )
    return [client._run_summary(r) for r in data.get("workflow_runs", [])]


# head SHA 가 바뀐 뒤에도 PR 의 run 을 찾는 이벤트 (옛 SHA 에서 돈 RELEASE run, #970)
_PR_RUN_EVENTS = ("pull_request", "pull_request_target")


def resolve_pr_runs(owner: str, repo: str, pr_number: int, pat: str) -> dict:
    """PR 번호 > run 목록: 현재 head SHA run + head 브랜치의 PR 이벤트 run (최신순, 중복 제거)

    run 마다 head_sha·is_current_head 를 붙인다. 브랜치 보강 조회 실패는 무시 (SHA run 만 반환)
    """
    pr = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}", None, pat)
    head_sha = pr["head"]["sha"]
    head_ref = pr["head"]["ref"]
    pr_created_at = pr.get("created_at") or ""
    by_sha = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/actions/runs?head_sha={head_sha}&per_page=30",
        None, pat,
    )
    raw_runs = list(by_sha.get("workflow_runs", []))
    # 같은 head 브랜치의 PR 이벤트 run (옛 SHA 포함)
    encoded_ref = urllib.parse.quote(head_ref, safe="")
    for event in _PR_RUN_EVENTS:
        try:
            by_branch = client._request(
                "GET",
                f"{_API_BASE}/repos/{owner}/{repo}/actions/runs?branch={encoded_ref}&event={event}&per_page=20",
                None, pat,
            )
        except client.GitHubAPIError:
            continue
        for run in by_branch.get("workflow_runs", []):
            linked_numbers = [linked.get("number") for linked in run.get("pull_requests") or []]
            # 다른 PR 의 run 제외 (연결 정보 없으면 이 PR 생성 이후 run 만)
            is_this_pr = (pr_number in linked_numbers if linked_numbers
                          else (run.get("created_at") or "") >= pr_created_at)
            if is_this_pr:
                raw_runs.append(run)
    seen_run_ids: set = set()
    runs = []
    for run in sorted(raw_runs, key=lambda item: item.get("created_at") or "", reverse=True):
        if run["id"] in seen_run_ids:
            continue
        seen_run_ids.add(run["id"])
        runs.append({**client._run_summary(run), "head_sha": run.get("head_sha"),
                     "is_current_head": run.get("head_sha") == head_sha})
    return {
        "pr_number": pr_number,
        "head_sha": head_sha,
        "head_ref": head_ref,
        "runs": runs,
    }


def resolve_branch_runs(owner: str, repo: str, branch: str, pat: str, limit: int = 10) -> list[dict]:
    """브랜치명 → 해당 브랜치의 최근 run 목록을 반환한다."""
    enc = urllib.parse.quote(branch, safe="")
    data = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/actions/runs?branch={enc}&per_page={limit}",
        None, pat,
    )
    return [client._run_summary(r) for r in data.get("workflow_runs", [])]


# ── 워크플로우 실행·재실행·대기 (#939) ──

# wait 폴링 간격(초)
_RUN_POLL_SECONDS = 10


def list_runs(owner: str, repo: str, pat: str, workflow: str | None = None, branch: str | None = None,
              status: str | None = None, limit: int = 10) -> list[dict]:
    """최근 run 목록. workflow 는 파일명(예: build.yaml) 또는 id, status 는 queued·in_progress·completed·failure 등"""
    base = (f"{_API_BASE}/repos/{owner}/{repo}/actions/workflows/{urllib.parse.quote(workflow, safe='')}/runs"
            if workflow else f"{_API_BASE}/repos/{owner}/{repo}/actions/runs")
    query = [f"per_page={limit}"]
    if branch:
        query.append(f"branch={urllib.parse.quote(branch, safe='')}")
    if status:
        query.append(f"status={urllib.parse.quote(status, safe='')}")
    data = client._request("GET", f"{base}?{'&'.join(query)}", None, pat)
    return [client._run_summary(r) for r in data.get("workflow_runs", [])]


def dispatch_workflow(owner: str, repo: str, workflow: str, ref: str, inputs: dict | None, pat: str) -> dict:
    """workflow_dispatch 로 워크플로우를 실행한다 (204 응답, run id 는 돌려주지 않는다)"""
    payload: dict = {"ref": ref}
    if inputs:
        payload["inputs"] = inputs
    client._request(
        "POST", f"{_API_BASE}/repos/{owner}/{repo}/actions/workflows/{urllib.parse.quote(workflow, safe='')}/dispatches",
        payload, pat)
    return {"workflow": workflow, "ref": ref, "inputs": inputs or {}}


def rerun_run(owner: str, repo: str, run_id: int, pat: str, failed_only: bool = False) -> dict:
    """run 을 다시 돌린다. failed_only 면 실패한 job 만"""
    suffix = "rerun-failed-jobs" if failed_only else "rerun"
    client._request("POST", f"{_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/{suffix}", {}, pat)
    return {"run_id": run_id, "failed_only": failed_only}


def cancel_run(owner: str, repo: str, run_id: int, pat: str, is_force_cancel: bool = False) -> dict:
    """run 을 취소한다. is_force_cancel 이면 always() step 까지 멈추는 강제 취소"""
    suffix = "force-cancel" if is_force_cancel else "cancel"
    client._request("POST", f"{_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/{suffix}", {}, pat)
    return {"run_id": run_id, "force": is_force_cancel}


def wait_for_runs(owner: str, repo: str, run_ids: list[int], pat: str, timeout_seconds: int) -> dict:
    """여러 run 이 모두 끝날 때까지(최대 timeout_seconds) 폴링 > {runs, finished, pending_run_ids, waited_seconds}"""
    started = time.monotonic()
    while True:
        results = [client.get_run(owner, repo, run_id, pat) for run_id in run_ids]
        waited = int(time.monotonic() - started)
        pending = [run_id for run_id, result in zip(run_ids, results) if result.get("status") != "completed"]
        if not pending or waited + _RUN_POLL_SECONDS > timeout_seconds:
            return {"runs": results, "finished": not pending, "pending_run_ids": pending, "waited_seconds": waited}
        client._sleep(_RUN_POLL_SECONDS)


def wait_for_run(owner: str, repo: str, run_id: int, pat: str, timeout_seconds: int) -> dict:
    """run 이 끝날 때까지(최대 timeout_seconds) 도구 안에서 폴링한다. 끝났으면 get_run 결과 + finished"""
    waited = wait_for_runs(owner, repo, [run_id], pat, timeout_seconds)
    return {**waited["runs"][0], "finished": waited["finished"], "waited_seconds": waited["waited_seconds"]}
