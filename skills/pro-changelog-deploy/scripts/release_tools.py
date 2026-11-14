"""Release helpers: wrap release notes, check the branch pair, sync base (#945).

Gathers in one place what the agent typed by hand on every deploy (CodeRabbit marker block, base merge,
checking the branch pair is right).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from common.emit import emit
from release_language import BUILT_IN_HEADINGS, load_headings, resolve_notes_language

NOTES_MARKER = "Summary by CodeRabbit"
_NOTES_OPEN = "<!-- This is an auto-generated comment: release notes by coderabbit.ai -->"
_NOTES_CLOSE = "<!-- end of auto-generated comment: release notes by coderabbit.ai -->"


def read_repo_language(project_root: Path) -> str:
    """version.yml options.language > note language (canonical: release_language — same rule as workflow i18n, #977)"""
    return resolve_notes_language(project_root, load_headings(project_root))[0]


def wrap_release_notes(body: str, language: str = "ko") -> tuple[str, bool]:
    """(body, whether wrapped). Leaves the body as is if empty or already marked.

    The workflow depends on the marker block structure. Hand-written mistakes wipe the body or
    raise missing_coderabbit_summary, so the tool wraps it instead.
    """
    if not body.strip() or NOTES_MARKER in body:
        return body, False
    inner = body.strip()
    if not inner.startswith("##"):
        heading = (BUILT_IN_HEADINGS.get(language) or BUILT_IN_HEADINGS["en"])["heading"]
        inner = f"## {heading}\n\n" + inner
    return f"{_NOTES_OPEN}\n\n## {NOTES_MARKER}\n\n{inner}\n\n{_NOTES_CLOSE}\n", True


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def _ref_exists(root: Path, ref: str) -> bool:
    return _git(root, "rev-parse", "--verify", "--quiet", ref).returncode == 0


def _commit_count(root: Path, exclude: str, include: str) -> int | None:
    done = _git(root, "rev-list", "--count", f"{exclude}..{include}")
    return int(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip().isdigit() else None


# Maximum time branches_check waits for fetch (so detect does not hang on a slow network)
_FETCH_TIMEOUT_SECONDS = 30


def _fetch_origin(root: Path) -> str | None:
    """git fetch origin (updates remote-tracking refs only). None on success, reason on failure"""
    try:
        done = subprocess.run(["git", "-C", str(root), "fetch", "--quiet", "origin"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=_FETCH_TIMEOUT_SECONDS)
    except (subprocess.TimeoutExpired, OSError) as error:
        return type(error).__name__
    return None if done.returncode == 0 else (done.stderr.strip().splitlines() or ["fetch failed"])[0][:200]


def branches_check(project_root: Path, head: str, base: str) -> dict:
    """Whether the configured head/base pair actually has a difference to release. Based on origin/* tracking refs after fetch (#1176)"""
    head_ref, base_ref = f"origin/{head}", f"origin/{base}"
    fetch_error = _fetch_origin(project_root)
    # Continue on failure: count with local refs and warn they may be stale
    stale_note = "" if fetch_error is None else f" (git fetch failed: {fetch_error}; counts come from local refs and may be stale)"
    out = {"fetched": fetch_error is None, "head_exists": _ref_exists(project_root, head_ref),
           "base_exists": _ref_exists(project_root, base_ref),
           "ahead_count": None, "behind_count": None, "warning": None}
    if not (out["head_exists"] and out["base_exists"]):
        missing = [r for r, ok in ((head_ref, out["head_exists"]), (base_ref, out["base_exists"])) if not ok]
        out["warning"] = f"{', '.join(missing)} not found. Check the development/default branches in version.yml{stale_note}"
        return out
    out["ahead_count"] = _commit_count(project_root, base_ref, head_ref)
    out["behind_count"] = _commit_count(project_root, head_ref, base_ref)
    if out["ahead_count"] == 0:
        out["warning"] = (f"{head_ref} has no commits ahead of {base_ref}; there may be nothing to release, or "
                          f"the branch pair may be wrong (confirm this repo's real release flow with the user){stale_note}")
    elif stale_note:
        out["warning"] = stale_note.strip(" ()")
    return out


# Deploy branch name in deploy-branch repos (development on the default branch, deploys via PR to this branch)
DEPLOY_BRANCH_NAME = "deploy"
_DEPLOY_TRIGGER_RE = re.compile(r"^\s+deploy_trigger_branch\s*:\s*[\"']?([A-Za-z0-9._/-]+)", re.MULTILINE)


def read_deploy_trigger_branch(project_root: Path) -> str | None:
    """version.yml options.deploy_trigger_branch (#1114). None if absent"""
    try:
        text = (project_root / "version.yml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _DEPLOY_TRIGGER_RE.search(text)
    return m.group(1) if m else None


def detect_release_shape(project_root: Path, branches: dict, check: dict) -> dict:
    """Release layout: standard (development > default) | deploy_branch (default > deploy, #970) | three_tier (development > default > deploy, #1114)

    Deploy-branch layout if the development branch is not on origin and origin/deploy exists.
    Three tiers if the development branch exists and the deploy branch (deploy_trigger_branch, else deploy) is on origin too. Otherwise standard
    """
    is_deploy_branch_shape = (not check.get("head_exists")
                              and branches["head"] != DEPLOY_BRANCH_NAME
                              and _ref_exists(project_root, f"origin/{DEPLOY_BRANCH_NAME}"))
    if is_deploy_branch_shape:
        return _deploy_branch_shape(branches)
    trigger = read_deploy_trigger_branch(project_root) or DEPLOY_BRANCH_NAME
    is_three_tier_shape = (check.get("head_exists")
                           and trigger not in (branches["head"], branches["base"])
                           and _ref_exists(project_root, f"origin/{trigger}"))
    if is_three_tier_shape:
        return _three_tier_shape(branches, trigger)
    return {"release_shape": "standard"}


def _deploy_branch_shape(branches: dict) -> dict:
    # Development happens on the default branch; the release PR is default > deploy
    head = branches["base"] if branches["base"] != DEPLOY_BRANCH_NAME else "main"
    return {
        "release_shape": "deploy_branch",
        "release_branches": {"head": head, "base": DEPLOY_BRANCH_NAME},
        "release_steps": [
            f"follow the deploy mode steps as written with HEAD_BRANCH={head}, BASE_BRANCH={DEPLOY_BRANCH_NAME} "
            f"(do not use the missing {branches['head']} as head)",
            f"Step 1-1: sync-base --head {head} --base {DEPLOY_BRANCH_NAME}",
            f"Step 6: create-pr ... {head} {DEPLOY_BRANCH_NAME} (release notes in the body)",
            f"Step 7: deploy-status --pr N --base {DEPLOY_BRANCH_NAME} (this shape has no automerge: manual_merge_needed tells you to merge)",
            "confirm the pair once with the user (without version.yml, record it in the per-repo config)",
        ],
    }


def _three_tier_shape(branches: dict, trigger: str) -> dict:
    # The release PR (version finalize, notes) stays development > default; deploying runs separately as default > deploy branch
    head, base = branches["head"], branches["base"]
    return {
        "release_shape": "three_tier",
        "release_branches": {"head": head, "base": base},
        "promote_branches": {"head": base, "base": trigger},
        "release_steps": [
            f"run the normal deploy steps with HEAD_BRANCH={head}, BASE_BRANCH={base}: this release PR finalizes the version and notes, it does not deploy",
            f"after it merges, the deploy workflows run only when {base} reaches {trigger}: "
            f"create-pr ... {base} {trigger} (no release workflow runs on it, so it never automerges: merge it after the user confirms)",
            f"ask the user before promoting {base} > {trigger}; app store repos need an explicit deploy request",
        ],
    }


def cmd_sync_base(args) -> int:
    """Reverse merge base > head before deploy: fetch > check difference > merge. Stops on conflict without reverting."""
    root = Path(args.project_root).resolve() if args.project_root else Path.cwd()
    current = _git(root, "branch", "--show-current").stdout.strip()
    if current != args.head:
        return emit({"ok": False, "code": "wrong_branch", "current": current, "expected": args.head,
                     "error": "the current branch is not the release head (another session may have switched it)",
                     "next": "do not switch branches on your own; tell the user"})
    fetched = _git(root, "fetch", "origin")
    if fetched.returncode != 0:
        return emit({"ok": False, "code": "fetch_failed", "error": fetched.stderr.strip()[:300], "next": None})
    behind = _git(root, "log", "--oneline", f"origin/{args.head}..origin/{args.base}").stdout.strip().splitlines()
    if not behind:
        return emit({"ok": True, "code": "in_sync", "behind": [], "summary": f"origin/{args.base} is already included",
                     "next": "continue the deploy steps"})
    merged = _git(root, "merge", "--no-edit", f"origin/{args.base}")
    if merged.returncode == 0:
        return emit({"ok": True, "code": "merged", "behind": behind[:20],
                     "summary": f"merged {len(behind)} commit(s) from origin/{args.base}", "next": "push, then continue the deploy steps"})
    conflicted = _git(root, "diff", "--name-only", "--diff-filter=U").stdout.split()
    if not conflicted:
        # Failure with no conflicting files is not a conflict but another cause (no commit author, hooks, dirty worktree etc.)
        return emit({"ok": False, "code": "merge_failed", "behind": behind[:20],
                     "error": (merged.stderr or merged.stdout).strip()[:400],
                     "next": "read the cause and fix it (git config user.name/email, overlapping uncommitted changes, ...). It is not a conflict, so there is nothing to abort"})
    return emit({"ok": False, "code": "merge_conflict", "conflicted_files": conflicted[:30], "behind": behind[:20],
                 "error": "merge conflict", "next": "resolve the conflict keeping both sides' intent, or decide with the user (do not merge --abort or reset on your own)"})
