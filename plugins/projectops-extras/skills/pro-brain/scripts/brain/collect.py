"""Metadata collection for one issue: commit range > changed files > stacks and modules > flat frontmatter lines
Flat keys only (scalars and flow lists): vault validators such as the passQL one reject nested maps.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .repo_facts import GitError, run_git

# Asia/Seoul has no DST, so a fixed offset avoids needing tzdata on Windows
SEOUL = timezone(timedelta(hours=9), "Asia/Seoul")
ISSUE_LOG_LIMIT = 400          # commits scanned when matching by issue URL
MODULE_LIMIT = 10              # changed_modules entries kept
MAIN_FILE_LIMIT = 8            # main_files entries kept (by lines changed)
# Branch name YYYYMMDD_#123_title > 123
BRANCH_ISSUE_PATTERN = re.compile(r"#(\d+)")


class RangeError(Exception):
    pass


def issue_from_branch(branch: str | None) -> int | None:
    match = BRANCH_ISSUE_PATTERN.search(branch or "")
    return int(match.group(1)) if match else None


def _rev(repo_root: Path, ref: str) -> str:
    return run_git(repo_root, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def _first_existing(repo_root: Path, refs: list[str]) -> str | None:
    for ref in refs:
        try:
            return _rev(repo_root, ref)
        except GitError:
            continue
    return None


def resolve_range(repo_root: Path, base: str | None, head: str | None, issue: int | None,
                  branch: str | None, development_branch: str | None, default_branch: str | None) -> dict:
    """Range modes 3: explicit base..head > commits whose message links issues/<N> > issue branch merge-base"""
    head_ref = head or "HEAD"
    head_sha = _rev(repo_root, head_ref)
    if base:
        base_sha = _rev(repo_root, base)
        shas = run_git(repo_root, "rev-list", f"{base_sha}..{head_sha}").split()
        return {"mode": "explicit", "base": base_sha, "head": head_sha, "commits": shas}
    if issue:
        pattern = f"issues/{issue}([^0-9]|$)"
        shas = run_git(repo_root, "log", head_sha, "-E", f"--grep={pattern}", "--format=%H",
                       f"-n{ISSUE_LOG_LIMIT}").split()
        if shas:
            oldest = shas[-1]
            base_sha = _first_existing(repo_root, [f"{oldest}^"]) or oldest
            return {"mode": "issue-commits", "base": base_sha, "head": shas[0], "commits": shas}
    development = development_branch or "develop"
    shared_branches = {development, default_branch or "main", "main", "deploy"}
    if branch and branch not in shared_branches:
        target = _first_existing(repo_root, [f"origin/{development}", development, f"origin/{default_branch or 'main'}"])
        if target:
            base_sha = run_git(repo_root, "merge-base", head_sha, target).strip()
            shas = run_git(repo_root, "rev-list", f"{base_sha}..{head_sha}").split()
            return {"mode": "branch", "base": base_sha, "head": head_sha, "commits": shas}
    raise RangeError("cannot tell the issue's commits apart: pass --base <sha before the first issue commit> "
                     "(and --head), or --issue N when commit messages link the issue URL")


def _numstat_rows(text: str) -> list[tuple[int, str]]:
    rows = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        # Renames show as "old => new" or "dir/{old => new}"; keep the new side
        path = re.sub(r"\{[^{}]*=> ([^{}]*)\}", r"\1", path)
        path = path.split(" => ")[-1].replace("//", "/")
        lines_changed = (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)
        rows.append((lines_changed, path))
    return rows


def changed_files(repo_root: Path, commit_range: dict, knowledge_path: str) -> dict[str, int]:
    """path > lines changed; issue-commits mode sums only the matched commits (unrelated commits in between are left out)"""
    totals: dict[str, int] = {}
    if commit_range["mode"] == "issue-commits":
        chunks = [run_git(repo_root, "show", "--numstat", "--format=", sha) for sha in commit_range["commits"]]
    else:
        chunks = [run_git(repo_root, "diff", "--numstat", commit_range["base"], commit_range["head"])]
    prefix = knowledge_path.strip("/") + "/"
    for chunk in chunks:
        for lines_changed, path in _numstat_rows(chunk):
            if path.startswith(prefix):
                continue   # the knowledge notes themselves are not code changes
            totals[path] = totals.get(path, 0) + lines_changed
    return totals


def stack_paths(registry_repo: dict, version_facts: dict) -> list[tuple[str, str]]:
    """(type, folder) pairs: registry stacks first, then version.yml project_paths, then project_types at the root"""
    stacks = [(str(item.get("type")), str(item.get("path") or ".")) for item in registry_repo.get("stacks") or []
              if isinstance(item, dict) and item.get("type")]
    if stacks:
        return stacks
    if version_facts["project_paths"]:
        return list(version_facts["project_paths"].items())
    return [(project_type, ".") for project_type in version_facts["project_types"]]


def _under(path: str, folder: str) -> bool:
    folder = folder.strip("/")
    return folder in ("", ".") or path == folder or path.startswith(folder + "/")


def summarize_changes(files: dict[str, int], stacks: list[tuple[str, str]]) -> dict:
    """stacks touched, modules (stack folder + next segment, else first segment) and main files"""
    touched = [stack_type for stack_type, folder in stacks if any(_under(path, folder) for path in files)]
    module_counts: dict[str, int] = {}
    for path in files:
        folder = next((f.strip("/") for _, f in stacks if f.strip("/") not in ("", ".") and _under(path, f)), None)
        if folder:
            rest = path[len(folder) + 1:].split("/")
            module = folder if len(rest) == 1 else f"{folder}/{rest[0]}"
        else:
            module = path.split("/")[0] if "/" in path else "(root)"
        module_counts[module] = module_counts.get(module, 0) + 1
    modules = sorted(module_counts, key=lambda name: (-module_counts[name], name))[:MODULE_LIMIT]
    main_files = sorted(files, key=lambda name: (-files[name], name))[:MAIN_FILE_LIMIT]
    return {"stacks": list(dict.fromkeys(touched)), "changed_modules": modules, "main_files": main_files,
            "changed_file_count": len(files)}


def now_seoul() -> datetime:
    return datetime.now(SEOUL)


def _yaml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(str(item), ensure_ascii=False) for item in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


# Frontmatter keys pro-brain owns, in output order. None of them collide with common vault keys
# (type, id, created, topics, status, related, source, resolves), so a repo's own schema stays intact.
METADATA_KEYS = ("project", "stacks", "app_version", "build_number", "issue", "issue_url", "pr", "pr_url", "branch",
                 "commit_base", "commit_head", "commit_count", "deploy_target", "deploy_version",
                 "changed_modules", "main_files", "captured_at", "captured_by")


def frontmatter_lines(metadata: dict) -> list[str]:
    """metadata > flat YAML lines (absent values left out; double-quoted strings are valid YAML and JSON)"""
    return [f"{key}: {_yaml_value(metadata[key])}" for key in METADATA_KEYS
            if metadata.get(key) not in (None, "", [])]
