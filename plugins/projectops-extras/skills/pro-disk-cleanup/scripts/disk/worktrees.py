"""worktree facts: find repos > worktree list > branch, issue number, changes, in use, recent activity"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from . import generated, shell, sizes
from .processes import ProcessSnapshot

# Branch rule YYYYMMDD_#number_title (# optional)
ISSUE_BRANCH_PATTERN = re.compile(r"^\d{8}_#?(\d+)_")
REMOTE_SLUG_PATTERN = re.compile(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$")
# Depth to search for repos (from the search root)
REPOSITORY_SEARCH_DEPTH = 2
# Number of changed-file examples
CHANGE_SAMPLE_COUNT = 8


def find_main_repositories(roots: list[Path]) -> list[Path]:
    """Folders with .git under the search root > main repo paths via the common git dir (deduplicated)"""
    repositories: dict[str, Path] = {}
    for root in roots:
        pending = [(root, 0)]
        while pending:
            current, depth = pending.pop()
            if (current / ".git").exists():
                code, common = shell.git(str(current), "rev-parse", "--path-format=absolute", "--git-common-dir")
                if code == 0 and common:
                    main = Path(common).parent
                    repositories[str(main.resolve())] = main.resolve()
                continue
            if depth >= REPOSITORY_SEARCH_DEPTH:
                continue
            try:
                with os.scandir(current) as entries:
                    pending += [(Path(entry.path), depth + 1) for entry in entries
                                if entry.is_dir(follow_symlinks=False) and not entry.name.startswith(".")
                                and entry.name not in generated.GENERATED_FOLDER_NAMES]
            except OSError:
                continue  # folder without permission
    return sorted(repositories.values())


def list_worktrees(main_repository: Path) -> list[dict]:
    """git worktree list --porcelain > [{path, branch, head, is_detached, is_locked, is_prunable}]"""
    code, out = shell.git(str(main_repository), "worktree", "list", "--porcelain")
    if code != 0:
        return []
    entries, current = [], {}
    for line in out.splitlines() + [""]:
        if not line:
            if current:
                entries.append(current)
            current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current = {"path": value, "branch": None, "head": None, "is_detached": False,
                       "is_locked": False, "is_prunable": False}
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key == "HEAD":
            current["head"] = value
        elif key == "detached":
            current["is_detached"] = True
        elif key == "locked":
            current["is_locked"] = True
        elif key == "prunable":
            current["is_prunable"] = True
    return entries


def repository_slug(main_repository: Path) -> str | None:
    _, url = shell.git(str(main_repository), "remote", "get-url", "origin")
    match = REMOTE_SLUG_PATTERN.search(url) if url else None
    return f"{match.group(1)}/{match.group(2)}" if match else None


def _changes(worktree: Path) -> dict:
    """git status > split real changes from generated-output changes"""
    # Leading space on the first line is the status column, so use run instead of shell.git (which strips)
    code, out, _ = shell.run(["git", "-c", "core.quotepath=false", "-C", str(worktree),
                              "status", "--porcelain", "--untracked-files=all"])
    if code != 0:
        return {"status_error": True, "real": [], "generated_count": 0}
    real, generated_count = [], 0
    for line in out.splitlines():
        relative = line[3:].split(" -> ")[-1].strip('"')
        if generated.is_generated_path(relative):
            generated_count += 1
        else:
            real.append(line)
    return {"status_error": False, "real": real, "generated_count": generated_count}


def _last_activity_seconds(worktree: Path, real_changes: list[str]) -> float | None:
    # Most recent of git index (checkout, staging) + modification times of changed files
    times = []
    _, git_dir = shell.git(str(worktree), "rev-parse", "--path-format=absolute", "--git-dir")
    for candidate in (Path(git_dir) / "index", Path(git_dir) / "HEAD") if git_dir else ():
        try:
            times.append(candidate.stat().st_mtime)
        except OSError:
            pass  # missing files are left out of the time candidates
    for line in real_changes:
        try:
            times.append((worktree / line[3:].split(" -> ")[-1].strip('"')).stat().st_mtime)
        except OSError:
            continue  # deleted changed file
    return max(times) if times else None


def describe_worktree(entry: dict, main_repository: Path, slug: str | None, snapshot: ProcessSnapshot,
                      idle_hours: float, should_measure_size: bool) -> dict:
    path = Path(entry["path"])
    is_main = path.resolve() == main_repository
    branch = entry.get("branch")
    match = ISSUE_BRANCH_PATTERN.match(branch or "")
    facts = {"path": str(path), "repository": slug, "main_repository": str(main_repository), "is_main": is_main,
             "branch": branch, "head": entry.get("head"), "is_detached": entry["is_detached"], "is_locked": entry["is_locked"],
             "is_missing": not path.exists(), "issue_number": int(match.group(1)) if match else None}
    if facts["is_missing"]:
        return facts
    changes = _changes(path)
    _, commit_time = shell.git(str(path), "log", "-1", "--format=%ct")
    _, unpushed = shell.git(str(path), "rev-list", "--count", "HEAD", "--not", "--remotes")
    activity = _last_activity_seconds(path, changes["real"])
    users = snapshot.users_of(path)
    facts.update({
        "last_commit_days": sizes.age_days(float(commit_time)) if commit_time.isdigit() else None,
        "last_activity_days": sizes.age_days(activity),
        "is_recently_active": bool(activity and time.time() - activity < idle_hours * 3600),
        "unpushed_commit_count": int(unpushed) if unpushed.isdigit() else None,
        "real_change_count": len(changes["real"]), "real_change_sample": changes["real"][:CHANGE_SAMPLE_COUNT],
        "generated_change_count": changes["generated_count"], "status_error": changes["status_error"],
        "in_use_by": users, "is_in_use": None if users is None else bool(users),
    })
    if should_measure_size:
        byte_count, is_partial = sizes.folder_bytes(path)
        facts.update({"size_gb": sizes.to_gigabytes(byte_count), "is_partial_size": is_partial})
    return facts


def collect(roots: list[Path], idle_hours: float, should_measure_size: bool, snapshot: ProcessSnapshot | None = None) -> list[dict]:
    snapshot = snapshot or ProcessSnapshot()
    results = []
    for main in find_main_repositories(roots):
        slug = repository_slug(main)
        for entry in list_worktrees(main):
            results.append(describe_worktree(entry, main, slug, snapshot, idle_hours, should_measure_size))
    return results


def find_one(path: Path, idle_hours: float) -> dict | None:
    """Facts for one path if it is a registered worktree, else None"""
    code, common = shell.git(str(path), "rev-parse", "--path-format=absolute", "--git-common-dir")
    if code != 0 or not common:
        return None
    main = Path(common).parent.resolve()
    for entry in list_worktrees(main):
        if Path(entry["path"]).resolve() == path.resolve():
            return describe_worktree(entry, main, repository_slug(main), ProcessSnapshot(), idle_hours, False)
    return None
