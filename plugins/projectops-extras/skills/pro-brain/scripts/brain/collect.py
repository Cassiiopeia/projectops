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
# Folder names that say nothing about the topic, so they never become a tag
GENERIC_FOLDER_NAMES = {"src", "main", "java", "kotlin", "lib", "app", "test", "tests", "resources", "(root)", "root"}
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
                  branch: str | None, development_branch: str | None, default_branch: str | None,
                  commits: list[str] | None = None, last_captured_head: str | None = None) -> dict:
    """Range modes 5: explicit base..head > listed commits > commits linking issues/<N> > issue branch merge-base
    > change set since the last captured note (session-end and merge capture on a shared branch)"""
    head_ref = head or "HEAD"
    head_sha = _rev(repo_root, head_ref)
    if base:
        base_sha = _rev(repo_root, base)
        shas = run_git(repo_root, "rev-list", f"{base_sha}..{head_sha}").split()
        return {"mode": "explicit", "base": base_sha, "head": head_sha, "commits": shas}
    if commits:
        # Topic group of a change set: only these commits count, newest first like rev-list
        full = [_rev(repo_root, sha) for sha in commits]
        ordered = [sha for sha in run_git(repo_root, "rev-list", "--no-walk=sorted", *full).split()]
        oldest = ordered[-1]
        return {"mode": "commit-list", "base": _first_existing(repo_root, [f"{oldest}^"]) or oldest,
                "head": ordered[0], "commits": ordered}
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
        target = _first_existing(repo_root, [f"origin/{development}", development, f"origin/{default_branch or 'main'}",
                                             default_branch or "main"])
        if target:
            base_sha = run_git(repo_root, "merge-base", head_sha, target).strip()
            shas = run_git(repo_root, "rev-list", f"{base_sha}..{head_sha}").split()
            if shas:
                return {"mode": "branch", "base": base_sha, "head": head_sha, "commits": shas}
    if last_captured_head:
        shas = run_git(repo_root, "rev-list", f"{last_captured_head}..{head_sha}").split()
        if shas:
            return {"mode": "since-last-note", "base": last_captured_head, "head": head_sha, "commits": shas}
    raise RangeError("cannot tell which commits this note covers: pass --base <sha before the first commit> "
                     "(and --head), --commits a,b,c for a topic group, or --issue N when commit messages link the issue URL")


def find_merge_commit(repo_root: Path, head_sha: str, targets: list[str]) -> str | None:
    """First merge commit on a target branch that brought head in (absent while the branch is unmerged)"""
    for target in targets:
        try:
            merges = run_git(repo_root, "rev-list", "--ancestry-path", "--merges", "--reverse",
                             f"{head_sha}..{target}").split()
        except GitError:
            continue
        if merges:
            return merges[0]
    return None


def commit_outline(repo_root: Path, commit_range: dict, limit: int = 60) -> list[dict]:
    """Short sha, subject and top folders per commit, so the agent can group a change set by topic"""
    outline = []
    for sha in commit_range["commits"][:limit]:
        subject = run_git(repo_root, "log", "-1", "--format=%s", sha).strip()
        paths = run_git(repo_root, "show", "--name-only", "--format=", sha).split("\n")
        folders = sorted({path.split("/")[0] if "/" in path else "(root)" for path in paths if path.strip()})
        outline.append({"sha": sha[:9], "subject": subject[:160], "folders": folders[:6]})
    return outline


def _numstat_rows(text: str) -> list[tuple[int, int, str]]:
    rows = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        # Renames show as "old => new" or "dir/{old => new}"; keep the new side
        path = re.sub(r"\{[^{}]*=> ([^{}]*)\}", r"\1", path)
        path = path.split(" => ")[-1].replace("//", "/")
        rows.append((int(added) if added.isdigit() else 0, int(deleted) if deleted.isdigit() else 0, path))
    return rows


def changed_files(repo_root: Path, commit_range: dict, knowledge_path: str) -> dict[str, tuple[int, int]]:
    """path > (added, deleted); issue and commit-list modes sum only the matched commits (unrelated ones left out)"""
    totals: dict[str, tuple[int, int]] = {}
    if commit_range["mode"] in ("issue-commits", "commit-list"):
        chunks = [run_git(repo_root, "show", "--numstat", "--format=", sha) for sha in commit_range["commits"]]
    else:
        chunks = [run_git(repo_root, "diff", "--numstat", commit_range["base"], commit_range["head"])]
    prefix = knowledge_path.strip("/") + "/"
    for chunk in chunks:
        for added, deleted, path in _numstat_rows(chunk):
            if path.startswith(prefix):
                continue   # the knowledge notes themselves are not code changes
            previous_added, previous_deleted = totals.get(path, (0, 0))
            totals[path] = (previous_added + added, previous_deleted + deleted)
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


def summarize_changes(files: dict[str, tuple[int, int]], stacks: list[tuple[str, str]]) -> dict:
    """stacks touched, modules (stack folder + next segment, else first segment), main files and line totals"""
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
    main_files = sorted(files, key=lambda name: (-sum(files[name]), name))[:MAIN_FILE_LIMIT]
    return {"stacks": list(dict.fromkeys(touched)), "changed_modules": modules, "main_files": main_files,
            "changed_file_count": len(files), "lines_added": sum(added for added, _ in files.values()),
            "lines_deleted": sum(deleted for _, deleted in files.values())}


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


# Frontmatter keys the CLI fills, in output order. None of them collide with common vault keys
# (type, id, title, created, topics, status, related, supersedes, source, resolves): those belong to the note
# template or the repo's own schema, so a repo's vault rules stay intact and these are extra keys.
METADATA_KEYS = ("capture_mode", "captured_at", "captured_by", "project", "stacks", "app_version", "build_number",
                 "issue", "issue_url", "pr", "pr_url", "branch", "commit_base", "commit_head", "commit_count", "commits",
                 "merge_commit", "changed_modules", "main_files", "lines_added", "lines_deleted",
                 "api_endpoints", "db_migrations", "config_keys", "env_or_secret_names", "feature_flags",
                 "deployed", "deploy_targets", "deploy_version")


def frontmatter_lines(metadata: dict) -> list[str]:
    """metadata > flat YAML lines (absent values left out; double-quoted strings are valid YAML and JSON)"""
    return [f"{key}: {_yaml_value(metadata[key])}" for key in METADATA_KEYS
            if metadata.get(key) not in (None, "", [])]


def topic_hints(changes: dict, contract_changes: dict) -> list[str]:
    """Search tags derived from what changed: stacks, module names, contract kinds (kebab-case, no LLM)"""
    hints = list(changes["stacks"])
    for module in changes["changed_modules"]:
        segments = [segment for segment in module.rstrip("/").split("/")
                    if segment.lower() not in GENERIC_FOLDER_NAMES and not segment.startswith(".")]
        if not segments:
            continue
        leaf = segments[-1]
        hints.append(re.sub(r"[^a-z0-9]+", "-", re.sub(r"([a-z])([A-Z])", r"\1-\2", leaf).lower()).strip("-"))
    for kind, tag in (("api_endpoints", "api"), ("db_migrations", "db-migration"), ("config_keys", "config"),
                      ("env_or_secret_names", "env"), ("feature_flags", "feature-flag")):
        if contract_changes.get(kind):
            hints.append(tag)
    return [hint for hint in dict.fromkeys(hints) if hint and hint != "root"]


def suggest_note_identity(issue: int | None, commit_range: dict, created: str, title_hint: str | None) -> dict:
    """Stable id and default file name: issue-<N> for an issue, change-<date>-<head sha> for a change set"""
    slug = re.sub(r"[^a-z0-9]+", "-", (title_hint or "").lower()).strip("-")
    slug = "-".join(slug.split("-")[:6])
    if issue:
        note_id = f"issue-{issue}"
        file_name = f"{created}-issue-{issue}{'-' + slug if slug else ''}.md"
    else:
        note_id = f"change-{created.replace('-', '')}-{commit_range['head'][:7]}"
        file_name = f"{created}-change-{commit_range['head'][:7]}{'-' + slug if slug else ''}.md"
    return {"id": note_id, "file_name": file_name}
