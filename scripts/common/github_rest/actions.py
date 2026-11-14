"""GitHub Actions: run details, job logs, failed runs, runs per PR/branch."""

from __future__ import annotations

import re
import time
import urllib.parse

from common import gh_client as client
from common.github_rest.transport import _API_BASE


def _run_summary(run: dict) -> dict:
    """Extract only the summary fields from a workflow run object."""
    head_repository = (run.get("head_repository") or {}).get("full_name")
    base_repository = (run.get("repository") or {}).get("full_name")
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
        "actor": (run.get("actor") or {}).get("login"),
        "triggering_actor": (run.get("triggering_actor") or {}).get("login"),
        "head_repository": head_repository,
        "is_fork": bool(head_repository and base_repository and head_repository != base_repository),
        "pull_requests": [pr.get("number") for pr in run.get("pull_requests") or []],
    }


def get_run(owner: str, repo: str, run_id: int, pat: str) -> dict:
    """Return a single run's metadata + job list (including failed steps)."""
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


# Default log search: failure lines (the marker GitHub leaves on failed steps)
ERROR_MARKER = "##[error]"
# Number of output lines to show before a ##[error] line (around the failed step)
_ERROR_CONTEXT_LINES = 8
# Default search when there is no ##[error]
_FALLBACK_PATTERN = "error|failed"


def get_job_log(
    owner: str, repo: str, job_id: int, pat: str,
    grep: str | None = None, tail: int = 30, save_to: str | None = None,
) -> dict:
    """Fetch a job log and return the last tail lines matching grep.

    No grep (default): ##[error] lines and the output lines before them. `##[group]Run` script source sections are skipped
    (so `error` text or branch names in the source do not match). With grep: regex search over all lines.
    The job logs endpoint redirects to Azure, so _request's strip handler is required.
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
        # Full log goes to a file: not all of it fits in the response, but it can be grepped later (#939)
        from pathlib import Path
        Path(save_to).write_text(text, encoding="utf-8")
        result["saved_to"] = save_to
    return result


def _output_line_indexes(lines: list[str]) -> list[int]:
    """Line numbers outside `##[group]Run …` ~ `##[endgroup]` (executed script source)"""
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
    """##[error] lines + the output lines before them (script source excluded). Without ##[error], search error|failed instead"""
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
    """(line predicate, whether parsed as regex). Case-insensitive, accepts regexes like `a|b`, an invalid regex is matched literally (#939)"""
    try:
        pattern = re.compile(grep, re.IGNORECASE)
        return (lambda line: pattern.search(line) is not None), True
    except re.error:
        needle = grep.lower()
        return (lambda line: needle in line.lower()), False


def list_failed_runs(owner: str, repo: str, pat: str, limit: int = 10) -> list[dict]:
    """Return the list of recently failed (conclusion=failure) runs."""
    data = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/actions/runs?status=failure&per_page={limit}",
        None, pat,
    )
    return [client._run_summary(r) for r in data.get("workflow_runs", [])]


# Events that still find a PR's runs after its head SHA changed (RELEASE runs on an old SHA, #970)
_PR_RUN_EVENTS = ("pull_request", "pull_request_target")


def resolve_pr_runs(owner: str, repo: str, pr_number: int, pat: str) -> dict:
    """PR number > run list: runs on the current head SHA + PR-event runs on the head branch (newest first, deduplicated)

    Each run gets head_sha · is_current_head. Branch lookup failures are ignored (returns SHA runs only)
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
    # PR-event runs on the same head branch (old SHAs included)
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
            # Exclude other PRs' runs (without link info, only runs after this PR was created)
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
    """Branch name → return that branch's recent runs."""
    enc = urllib.parse.quote(branch, safe="")
    data = client._request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/actions/runs?branch={enc}&per_page={limit}",
        None, pat,
    )
    return [client._run_summary(r) for r in data.get("workflow_runs", [])]


# ── Run, rerun and wait for workflows (#939) ──

# wait polling interval (seconds)
_RUN_POLL_SECONDS = 10


def list_runs(owner: str, repo: str, pat: str, workflow: str | None = None, branch: str | None = None,
              status: str | None = None, limit: int = 10, event: str | None = None,
              created: str | None = None) -> list[dict]:
    """Recent runs. workflow is a file name (e.g. build.yaml) or id; status is queued · in_progress · completed · failure, etc."""
    base = (f"{_API_BASE}/repos/{owner}/{repo}/actions/workflows/{urllib.parse.quote(workflow, safe='')}/runs"
            if workflow else f"{_API_BASE}/repos/{owner}/{repo}/actions/runs")
    query = [f"per_page={limit}"]
    if branch:
        query.append(f"branch={urllib.parse.quote(branch, safe='')}")
    if status:
        query.append(f"status={urllib.parse.quote(status, safe='')}")
    if event:
        query.append(f"event={urllib.parse.quote(event, safe='')}")
    if created:
        query.append(f"created={urllib.parse.quote(created, safe='')}")
    data = client._request("GET", f"{base}?{'&'.join(query)}", None, pat)
    return [client._run_summary(r) for r in data.get("workflow_runs", [])]


def dispatch_workflow(owner: str, repo: str, workflow: str, ref: str, inputs: dict | None, pat: str) -> dict:
    """Run a workflow via workflow_dispatch (204 response; no run id is returned)"""
    payload: dict = {"ref": ref}
    if inputs:
        payload["inputs"] = inputs
    client._request(
        "POST", f"{_API_BASE}/repos/{owner}/{repo}/actions/workflows/{urllib.parse.quote(workflow, safe='')}/dispatches",
        payload, pat)
    return {"workflow": workflow, "ref": ref, "inputs": inputs or {}}


def rerun_run(owner: str, repo: str, run_id: int, pat: str, failed_only: bool = False) -> dict:
    """Rerun a run. With failed_only, only the failed jobs"""
    suffix = "rerun-failed-jobs" if failed_only else "rerun"
    client._request("POST", f"{_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/{suffix}", {}, pat)
    return {"run_id": run_id, "failed_only": failed_only}


def cancel_run(owner: str, repo: str, run_id: int, pat: str, is_force_cancel: bool = False) -> dict:
    """Cancel a run. With is_force_cancel, a force cancel that also stops always() steps"""
    suffix = "force-cancel" if is_force_cancel else "cancel"
    client._request("POST", f"{_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/{suffix}", {}, pat)
    return {"run_id": run_id, "force": is_force_cancel}


def wait_for_runs(owner: str, repo: str, run_ids: list[int], pat: str, timeout_seconds: int) -> dict:
    """Poll until all runs finish (at most timeout_seconds) > {runs, finished, pending_run_ids, waited_seconds}"""
    started = time.monotonic()
    while True:
        results = [client.get_run(owner, repo, run_id, pat) for run_id in run_ids]
        waited = int(time.monotonic() - started)
        pending = [run_id for run_id, result in zip(run_ids, results) if result.get("status") != "completed"]
        if not pending or waited + _RUN_POLL_SECONDS > timeout_seconds:
            return {"runs": results, "finished": not pending, "pending_run_ids": pending, "waited_seconds": waited}
        client._sleep(_RUN_POLL_SECONDS)


def wait_for_run(owner: str, repo: str, run_id: int, pat: str, timeout_seconds: int) -> dict:
    """Poll inside the tool until the run finishes (at most timeout_seconds). If finished, get_run result + finished"""
    waited = wait_for_runs(owner, repo, [run_id], pat, timeout_seconds)
    return {**waited["runs"][0], "finished": waited["finished"], "waited_seconds": waited["waited_seconds"]}
