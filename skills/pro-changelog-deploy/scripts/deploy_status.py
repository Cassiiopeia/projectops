"""deploy-status: judge a deploy PR's automerge state as one verdict (--wait polls inside the tool, #945)."""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.config import get_github_pat  # noqa: E402
from common.emit import emit  # noqa: E402
from common.gh_client import (  # noqa: E402
    GitHubAPIError, resolve_pr_runs, get_pull_detail, find_open_pr_by_base, get_branch_head, list_runs,
)

# An automerge wait beyond this is treated as blocked, not a normal wait (#945)
STUCK_AFTER_SECONDS = 600
# --wait poll interval and maximum wait per call (so it ends within the harness command time limit)
WAIT_POLL_SECONDS = 15
WAIT_MAX_SECONDS = 540
# Grace period (seconds) right after PR creation when the workflow may not be visible in the API yet
WORKFLOW_GRACE_SECONDS = 120
# Verdicts that are not final yet and worth waiting for
_STILL_WAITING_VERDICTS = ("waiting_for_automerge", "waiting_for_workflow")
# Run states before start / in progress
_RUNNING_STATUSES = ("in_progress", "queued", "waiting", "requested", "pending")
# RELEASE-CHANGELOG workflow files (new and old names, #455 rename)
_RELEASE_WORKFLOW_PATHS = ("project-common-release-changelog.yaml", "project-common-auto-changelog-control.yaml")
# Deploy-branch release PR (default > deploy): the RELEASE-CHANGELOG trigger does not accept this direction, so no automerge (#1077)
_BRANCH_WITHOUT_RELEASE_WORKFLOW = "deploy"


def _stuck_reason(pr_age_sec, workflow, workflow_running, mergeable_state):
    """Why the automerge wait got blocked once over the threshold. None if not blocked"""
    if pr_age_sec is None or pr_age_sec < STUCK_AFTER_SECONDS or workflow_running:
        return None
    if workflow is None:
        return "no_workflow_on_head"  # no RELEASE-CHANGELOG run for this PR anywhere on the head branch and the queue is empty
    if workflow.get("conclusion") == "success":
        return "workflow_done_not_merged"  # the workflow finished but the PR was not merged
    return None


def cmd_deploy_status(args) -> int:
    """Judge deploy PR state. With --wait N, poll inside the tool until done (up to N seconds) (#945)."""
    import time
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "no PAT configured"})
    wait_seconds = min(max(args.wait or 0, 0), WAIT_MAX_SECONDS)
    started = time.monotonic()
    try:
        while True:
            payload = _deploy_status_once(args, pat)
            waited = int(time.monotonic() - started)
            if payload.get("verdict") not in _STILL_WAITING_VERDICTS or waited + WAIT_POLL_SECONDS > wait_seconds:
                break
            time.sleep(WAIT_POLL_SECONDS)
        if wait_seconds:
            payload["waited_seconds"] = waited
        return emit(payload)
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def _is_release_run(run: dict) -> bool:
    """Is it a RELEASE-CHANGELOG run: file path first, name keyword as a fallback for old repos

    name is a human-facing label and changes — path is the identifier.
    """
    path = (run.get("path") or "").lower()
    name = (run.get("name") or "").upper()
    return path.endswith(_RELEASE_WORKFLOW_PATHS) \
        or ("CHANGELOG" in name and ("AUTO" in name or "DEPLOY" in name or "RELEASE" in name))


def _find_release_workflow(owner: str, repo: str, pr_number: int, pat: str) -> dict | None:
    """The PR's latest RELEASE-CHANGELOG run (current head SHA + head-branch PR event, newest first). None if absent"""
    try:
        runs = resolve_pr_runs(owner, repo, pr_number, pat).get("runs", [])
    except GitHubAPIError:
        return None
    for run in runs:
        if _is_release_run(run):
            return {
                "name": run.get("name"),
                "path": run.get("path"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "run_url": run.get("url"),
                "head_sha": run.get("head_sha"),
                # false if the run was on an old head SHA (head changed after a push)
                "is_current_head": run.get("is_current_head", True),
            }
    return None


def _count_repository_queued_runs(owner: str, repo: str, pat: str) -> int:
    """Number of queued runs repo-wide (for runner queue delay judgement). 0 if the lookup fails"""
    try:
        return len(list_runs(owner, repo, pat, status="queued", limit=20))
    except GitHubAPIError:
        return 0


def _deploy_status_once(args, pat) -> dict:
    """Return one lookup's verdict as a dict (the caller emits)."""
    if args.pr:
        pr = get_pull_detail(args.owner, args.repo, args.pr, pat)
    else:
        pr = find_open_pr_by_base(args.owner, args.repo, args.base, pat, head=args.head)
    branch_head = get_branch_head(args.owner, args.repo, args.base, pat)
    deploy_branch = {"name": args.base, "head_sha": branch_head}

    if pr is None:
        return {
            "pr": None,
            "workflow": None,
            "deploy_branch": deploy_branch,
            "verdict": "no_pr",
            "summary": f"no open PR into base={args.base}",
        }

    workflow = _find_release_workflow(args.owner, args.repo, pr["number"], pat)

    body = pr.get("body") or ""
    has_summary = "Summary by CodeRabbit" in body
    pr_out = {
        "number": pr["number"],
        "state": pr["state"],
        "merged": pr["merged"],
        "mergeable_state": pr["mergeable_state"],
        "has_coderabbit_summary": has_summary,
        "head_sha": pr["head_sha"],
        "url": pr["url"],
        "created_at": pr.get("created_at"),
    }

    workflow_status = (workflow or {}).get("status")
    workflow_conclusion = (workflow or {}).get("conclusion")
    workflow_running = workflow_status in _RUNNING_STATUSES

    # Right after PR creation the workflow may have just triggered and not yet show in the
    # API. Even with workflow=null, if the PR is freshly created, yield to waiting
    # instead of judging missing.
    import datetime as _dt
    pr_age_sec = None
    if pr.get("created_at"):
        try:
            created = _dt.datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
            now = _dt.datetime.now(_dt.timezone.utc)
            pr_age_sec = (now - created).total_seconds()
        except Exception:
            pr_age_sec = None
    pr_young = (pr_age_sec is not None and pr_age_sec < WORKFLOW_GRACE_SECONDS)
    # No matching run: check the repo queue (run not picked up yet for lack of runners, #970)
    repo_queued_count = 0
    if workflow is None and not pr_young:
        repo_queued_count = _count_repository_queued_runs(args.owner, args.repo, pat)

    next_hint = f"deploy-status {args.owner} {args.repo} --pr {pr['number']}"
    # Queue delay is not fixed by closing and reopening the PR — reopening only stacks another run (#970)
    wait_hint = (f"deploy-status {args.owner} {args.repo} --pr {pr['number']} --wait {WAIT_MAX_SECONDS} "
                 "(do not close or reopen the PR)")
    if pr["merged"]:
        verdict, summary = "merged", f"PR #{pr['number']} automerged"
        # Prevent missing the post-merge wrap-up (#970)
        next_hint = (f"for each issue in the release (issue URLs in the PR #{pr['number']} commit messages): "
                     "post a report comment with pro-report > finish it with pro-github finish-issue")
    elif pr["mergeable_state"] == "dirty":
        verdict = "conflict"
        summary = f"PR #{pr['number']} has merge conflicts (dirty)"
    elif pr["mergeable_state"] == "behind":
        verdict = "behind"
        summary = f"PR #{pr['number']} is behind base; merge base into head"
        next_hint = "git fetch origin && git merge origin/<base>, then push (it is only behind, no conflict)"
    elif pr["mergeable_state"] == "blocked":
        verdict = "blocked"
        summary = f"PR #{pr['number']} merge is blocked; it may be waiting on required checks, reviews or protection rules"
    elif workflow and workflow_conclusion == "failure":
        # Latest RELEASE run failed (even if it ran on an old head SHA, it counts as failed when no newer run exists)
        verdict = "workflow_failed"
        sha_note = "" if workflow.get("is_current_head") else " (run of an earlier head SHA)"
        summary = f"RELEASE-CHANGELOG workflow failed{sha_note}: {workflow.get('run_url')}"
        next_hint = "check the failure at workflow.run_url > rerun in fix mode"
    elif workflow_running:
        # While the workflow is queued or running, an empty-looking body/has_summary is a normal wait (race guard)
        verdict = "waiting_for_workflow"
        summary = f"PR #{pr['number']} RELEASE-CHANGELOG {workflow_status}; waiting for the workflow"
        next_hint = wait_hint
    elif workflow is None and (pr_young or repo_queued_count):
        # No matching run: just after PR creation (API delay) or runs backed up in the repo queue
        verdict = "waiting_for_workflow"
        reason = (f"just created ({int(pr_age_sec)}s)" if pr_young
                  else f"{repo_queued_count} run(s) queued in the repo")
        summary = f"PR #{pr['number']} {reason}; waiting for the workflow to start"
        next_hint = wait_hint
    elif workflow_conclusion == "skipped" or (workflow is None and args.base == _BRANCH_WITHOUT_RELEASE_WORKFLOW):
        # Nobody will merge even if we wait: report right away instead of wasting time (#1077)
        verdict = "manual_merge_needed"
        summary = f"PR #{pr['number']} will not automerge: no release workflow ran for {args.base}"
        next_hint = (f"Confirm with the user, then: github_cli.py merge-pr {args.owner} {args.repo} {pr['number']}. "
                     "Merging starts this repo's deploy workflow")
    elif not has_summary:
        # Not running and the PR is not fresh: judged as a real body-reset incident
        verdict = "missing_coderabbit_summary"
        summary = f"PR #{pr['number']} body has no 'Summary by CodeRabbit'; rewrite it in fix mode"
    else:
        verdict = "waiting_for_automerge"
        summary = f"PR #{pr['number']} open, {pr['mergeable_state']}; waiting for automerge"

    # Over the threshold: report blocked instead of waiting forever (#945)
    pr_out["age_seconds"] = int(pr_age_sec) if pr_age_sec is not None else None
    stuck = _stuck_reason(pr_age_sec, workflow, workflow_running, pr["mergeable_state"]) \
        if verdict == "waiting_for_automerge" else None
    if stuck:
        verdict = "stuck"
        summary = f"PR #{pr['number']} not automerged after {int(pr_age_sec)}s ({stuck})"
        next_hint = ("fix mode: close the existing PR and re-trigger the workflow with a new PR "
                     "(a fix push does not fire the opened trigger again)")

    return {
        "pr": pr_out,
        "workflow": workflow,
        "deploy_branch": deploy_branch,
        "verdict": verdict,
        **({"stuck_reason": stuck} if stuck else {}),
        "summary": summary,
        "next": next_hint,
    }
