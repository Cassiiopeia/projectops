"""create-pr: create the deploy PR with release notes in the body.

Order: check body file > app review approval gate > check existing PR > check commit difference > create > body re-injection guard
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.config import get_github_pat  # noqa: E402
from common.emit import emit  # noqa: E402
from common.gh_client import (  # noqa: E402
    GitHubAPIError, update_pull_request, create_pull_request, get_pull_detail, get_ahead_by,
    find_open_pr_by_base,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_context import APP_SIGNAL_HINTS, collect_app_signals, load_config, read_app_release  # noqa: E402
from release_tools import read_repo_language, wrap_release_notes  # noqa: E402

# Raw 422 text > meaningful code (#970)
_NO_COMMITS_MESSAGE = "No commits between"
_PR_EXISTS_MESSAGE = "pull request already exists"


def _resolve_body_file(body_file: str | None) -> Path | None:
    """Resolve the body file path — absolute paths as is, relative paths searched across several locations in order.

    The SKILL.md procedure saves to `~/.projectops/tmp/{owner}__{repo}__release_notes.md` (home, absolute path)
    and passes that absolute path to the cli. In case someone passes just a file name (relative), it also
    searches home tmp → PROJECT_ROOT/scripts (old-version compatibility) → cwd.
    Returns None if not found (the caller decides there is no body).
    """
    if not body_file:
        return None
    raw = Path(body_file)
    if raw.is_absolute():
        return raw if raw.exists() else None
    for candidate in (
        raw,
        Path.home() / ".projectops" / "tmp" / raw.name,
        Path.home() / ".suh-template" / "tmp" / raw.name,  # transitional fallback for the old path (#459 migration)
        _PROJECT_ROOT / "scripts" / raw.name,
        Path.cwd() / raw,
    ):
        if candidate.exists():
            return candidate
    return None


def _git_root_or_cwd() -> Path:
    """Read app signals from the repo root even if cwd is a subfolder"""
    import subprocess
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        top = ""
    return Path(top) if top else Path.cwd()


def _needs_app_release_approval(args) -> dict | None:
    """Rejection response if it is an app review repo without --user-approved, else None (#970)

    Condition: app_release record true, or app signals (strong_app·app_release_likely) with a record that is not false
    """
    if args.user_approved:
        return None
    project_root = Path(args.project_root).resolve() if args.project_root else _git_root_or_cwd()
    signals, hint = collect_app_signals(project_root)
    app_release = read_app_release(load_config(None), args.owner, args.repo)
    # unknown (neither version.yml nor workflows readable) = wrong root — block when there is no record (fail-closed)
    is_app_release = app_release is True or (
        (hint in APP_SIGNAL_HINTS or hint == "unknown") and app_release is not False)
    if not is_app_release:
        return None
    return {
        "ok": False, "code": "needs_user_approval",
        "summary": "this deploy leads to app store review; no PR without user approval",
        "error": "an app review repo needs user approval every time, even in auto mode (it goes straight to store review)",
        "hint": hint, "app_release": app_release, "signals": signals,
        "next": ("show the user the review warning banner and the release notes and get approval > "
                 "once approved, run the same create-pr command again with --user-approved"),
    }


def _pr_exists_response(args, pr_number, pr_url) -> dict:
    """Response when a PR from the same head > base is already open (#970)"""
    return {
        "ok": False, "code": "pr_exists", "number": pr_number, "url": pr_url,
        "summary": f"PR #{pr_number} is already open for {args.head} > {args.base}",
        "hint": "reuse it without closing; to change the notes, update only the body with update-pr",
        "next": f"deploy-status {args.owner} {args.repo} --pr {pr_number}",
    }


def _nothing_to_deploy_response(args) -> dict:
    """Response when there are no commits to release"""
    return {
        "ok": False, "code": "nothing_to_deploy",
        "summary": f"nothing to deploy: {args.head} has no commits ahead of {args.base}",
        "error": f"{args.head} has no commits ahead of {args.base}",
        "next": "check that the push went through and the branch pair is right with branches_check from detect-release-context",
    }


def _find_existing_pr(args, pat) -> dict | None:
    """Details of the open head > base PR. None if the lookup fails (caught again as 422 on create)"""
    try:
        return find_open_pr_by_base(args.owner, args.repo, args.base, pat, head=args.head)
    except GitHubAPIError:
        return None


def cmd_create_pr(args) -> int:
    """Create the deploy PR: validate > approval gate > check existing PR and commit difference > create > body re-injection guard"""
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "summary": "no PAT configured", "error": "no PAT configured"})
    body_path = _resolve_body_file(args.body_file)
    if args.body_file and not body_path:
        return emit({
            "ok": False, "code": "body_file_not_found",
            "summary": "body file not found",
            "error": (
                f"body file not found: {args.body_file} "
                f"(searched: absolute path | ~/.projectops/tmp/ | {_PROJECT_ROOT / 'scripts'} | cwd={Path.cwd()})"
            ),
        })
    body = body_path.read_text(encoding="utf-8") if body_path else ""

    # App review approval gate (before API calls)
    approval_refusal = _needs_app_release_approval(args)
    if approval_refusal:
        return emit(approval_refusal)

    # Do not create a new PR if one is already open (opening a new one re-triggers the workflow > body reset risk)
    existing_pr = _find_existing_pr(args, pat)
    if existing_pr:
        return emit(_pr_exists_response(args, existing_pr["number"], existing_pr.get("url")))

    # Do not create a PR when there are no commits to release (force only with --allow-empty)
    try:
        ahead_by = get_ahead_by(args.owner, args.repo, args.base, args.head, pat)
    except GitHubAPIError:
        ahead_by = None
    if ahead_by == 0 and not args.allow_empty:
        return emit(_nothing_to_deploy_response(args))
    # The tool wraps the marker block — hand-written ones go wrong and the body gets wiped
    project_root = Path(args.project_root).resolve() if args.project_root else _git_root_or_cwd()
    body, wrapped = wrap_release_notes(body, read_repo_language(project_root))
    try:
        result = create_pull_request(args.owner, args.repo, args.title, body, args.head, args.base, pat)
    except GitHubAPIError as e:
        # Raw 422 that slipped past the pre-checks > code (#970)
        if e.status_code == 422 and _NO_COMMITS_MESSAGE.lower() in e.message.lower():
            return emit(_nothing_to_deploy_response(args))
        if e.status_code == 422 and _PR_EXISTS_MESSAGE in e.message.lower():
            existing_pr = _find_existing_pr(args, pat)
            if existing_pr:
                return emit(_pr_exists_response(args, existing_pr["number"], existing_pr.get("url")))
        return emit({"ok": False, "code": f"github_api_{e.status_code}",
                     "summary": f"PR creation failed (HTTP {e.status_code})", "error": str(e)})

    pr_number = result.get("number")
    guard_summary = _reinject_body_if_cleared(args, pat, pr_number, body)
    out = {
        **result,
        "summary": f"created PR #{pr_number}" + (f" / {guard_summary}" if guard_summary else ""),
        "next": f"deploy-status {args.owner} {args.repo} --pr {pr_number}",
    }
    if wrapped:
        out["notes_wrapped"] = True
    if guard_summary:
        out["body_guard"] = guard_summary
    return emit(out)


def _reinject_body_if_cleared(args, pat, pr_number, body) -> str | None:
    """Re-inject the body if the workflow emptied it right after PR creation. Returns a result summary (None if no body)

    RELEASE-CHANGELOG step 2 can reset the body usually within 3~10 seconds after the PR opens.
    Check the body after 15 seconds and re-inject with update-pr if empty > step 8 polling catches the body on the first try.
    """
    if not (pr_number and body):
        return None
    import time
    time.sleep(15)
    try:
        detail = get_pull_detail(args.owner, args.repo, pr_number, pat)
        if "Summary by CodeRabbit" not in (detail.get("body") or ""):
            update_pull_request(args.owner, args.repo, pr_number, pat, body=body)
            return "body re-injected (recovered from the workflow step 2 race)"
        return "body intact; no re-injection needed"
    except GitHubAPIError:
        return "could not re-check the body; continuing"
