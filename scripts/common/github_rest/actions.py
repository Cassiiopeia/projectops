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


def get_job_log(
    owner: str, repo: str, job_id: int, pat: str,
    grep: str = "error", tail: int = 30, save_to: str | None = None,
) -> dict:
    """job 로그를 받아 grep 매칭 라인의 끝 tail개를 반환한다.

    job logs 엔드포인트는 Azure로 redirect되므로 _request의 strip 핸들러가 필수.
    """
    text = client._request(
        "GET", f"{_API_BASE}/repos/{owner}/{repo}/actions/jobs/{job_id}/logs", None, pat, raw=True
    )
    all_lines = text.splitlines()
    matches_line, is_regex = _line_matcher(grep)
    matched = [l for l in all_lines if matches_line(l)]
    result = {
        "job_id": job_id,
        "total_lines": len(all_lines),
        "matched_count": len(matched),
        "grep": grep,
        "regex": is_regex,
        "lines": [l[:300] for l in matched[-tail:]],
    }
    if save_to:
        # 전체 로그는 파일로: 응답에 다 싣지 않아도 나중에 직접 grep 할 수 있다 (#939)
        from pathlib import Path
        Path(save_to).write_text(text, encoding="utf-8")
        result["saved_to"] = save_to
    return result


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


def resolve_pr_runs(owner: str, repo: str, pr_number: int, pat: str) -> dict:
    """PR 번호 → head SHA → 연결된 run 목록을 반환한다."""
    pr = client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}", None, pat)
    head_sha = pr["head"]["sha"]
    head_ref = pr["head"]["ref"]
    runs = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/actions/runs?head_sha={head_sha}&per_page=30",
        None, pat,
    )
    return {
        "pr_number": pr_number,
        "head_sha": head_sha,
        "head_ref": head_ref,
        "runs": [client._run_summary(r) for r in runs.get("workflow_runs", [])],
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


def wait_for_run(owner: str, repo: str, run_id: int, pat: str, timeout_seconds: int) -> dict:
    """run 이 끝날 때까지(최대 timeout_seconds) 도구 안에서 폴링한다. 끝났으면 get_run 결과 + finished"""
    started = time.monotonic()
    while True:
        result = client.get_run(owner, repo, run_id, pat)
        waited = int(time.monotonic() - started)
        if result.get("status") == "completed":
            return {**result, "finished": True, "waited_seconds": waited}
        if waited + _RUN_POLL_SECONDS > timeout_seconds:
            return {**result, "finished": False, "waited_seconds": waited}
        client._sleep(_RUN_POLL_SECONDS)
