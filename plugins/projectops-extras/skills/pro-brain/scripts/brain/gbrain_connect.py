"""Connect the repo's knowledge folder to the user's own GBrain: one source `<project>-knowledge`, then sync
Plan by default; apply only after consent. Never overwrites a source, never passes --force, never touches hooks,
mounts, MCP settings or other sources. A remote (thin client) brain gets the commands to run on its host instead.
"""
from __future__ import annotations

from pathlib import Path

from . import brain_usage
from .repo_facts import GitError, current_branch, run_git

SOURCES_PARENT_EXAMPLE = "~/gbrain-sources"   # suggested home for dedicated default-branch clones


def default_source_id(project: str) -> str:
    return f"{project}-knowledge"


def _remote_url(repo_root: Path) -> str:
    try:
        return run_git(repo_root, "remote", "get-url", "origin").strip() or "<repo-url>"
    except GitError:
        return "<repo-url>"


def _has_committed_notes(source_root: Path, knowledge_path: str) -> bool:
    try:
        return bool(run_git(source_root, "ls-files", "--", knowledge_path).strip())
    except GitError:
        return False


def sync_recipe(repo_root: Path, project: str, source_id: str, knowledge_path: str, default_branch: str) -> dict:
    """Dedicated clone of the default branch, so the brain sees merged notes only (not whatever branch is checked out)"""
    clone = f"{SOURCES_PARENT_EXAMPLE}/{project}"
    return {
        "why": "gbrain reads the committed files of the branch checked out at the source path; a dedicated clone of "
               f"{default_branch} keeps work-in-progress branches out of the brain",
        "commands": [
            f"git clone --branch {default_branch} --single-branch {_remote_url(repo_root)} {clone}",
            f"gbrain sources add {source_id} --path {clone}/{knowledge_path.rstrip('/')}",
            f"gbrain sync --source {source_id} --no-pull",
        ],
        "schedule": f"git -C {clone} pull --ff-only --quiet && gbrain sync --source {source_id} --no-pull",
        "schedule_hint": "run the schedule line hourly (cron, launchd, Task Scheduler) or after each merge",
    }


def plan(repo_root: Path, knowledge_path: str, project: str, default_branch: str,
         source_id: str | None, source_root: str | None, is_remote: bool = False) -> dict:
    """Facts + verdict code: ready | already_connected | source_id_taken | folder_already_connected | no_notes_yet |
    remote_brain | brain_not_initialized | gbrain_missing | not_a_checkout"""
    source_id = source_id or default_source_id(project)
    root = Path(source_root).expanduser().resolve() if source_root else repo_root
    folder = root / knowledge_path
    detected = brain_usage.detect_gbrain()
    recipe = sync_recipe(repo_root, project, source_id, knowledge_path, default_branch)
    result = {"detected": detected, "source_id": source_id, "source_root": str(root), "source_path": str(folder),
              "checked_out_branch": current_branch(root) if root.is_dir() else None, "default_branch": default_branch,
              "default_branch_recipe": recipe}
    commands = [f"gbrain sources add {source_id} --path {folder}", f"gbrain sync --source {source_id} --no-pull"]
    if is_remote:
        # Own brain reached over HTTP from this machine (no local gbrain needed): the sync runs on its host
        detected = {**detected, "kind": "remote"}
    elif not detected["installed"]:
        return {**result, "code": "gbrain_missing", "commands": [],
                "summary": f"gbrain is not installed on this machine (install guide: {brain_usage.GBRAIN_INSTALL_URL})"}
    if detected["kind"] == "remote":
        return {**result, "code": "remote_brain", "commands": recipe["commands"],
                "summary": "this machine is a thin client of a remote brain: run the commands where that brain's "
                           "database is reachable (its host); nothing changes here, MCP settings stay as they are"}
    if detected["kind"] != "local":
        return {**result, "code": "brain_not_initialized", "commands": [],
                "summary": "gbrain is installed but has no brain yet: the user creates one (gbrain init), then run connect again"}
    if not detected["sources_readable"]:
        return {**result, "code": "sources_unreadable", "commands": [],
                "summary": "gbrain sources list failed, so a name clash cannot be ruled out: nothing is added"}
    same_id = next((source for source in detected["sources"] if source["id"] == source_id), None)
    if same_id:
        if _is_same_folder(same_id.get("local_path"), folder):
            return {**result, "code": "already_connected", "existing": same_id, "commands": [commands[1]],
                    "summary": f"source {source_id} already reads {folder}: only a sync is needed"}
        return {**result, "code": "source_id_taken", "existing": same_id, "commands": [],
                "summary": f"a source named {source_id} already exists and reads {same_id.get('local_path')}: "
                           "nothing was changed; pick another id with --source-id or inspect it with gbrain sources status"}
    # A source reading the folder, a part of it, or the repo around it would import the same notes twice
    other = next((source for source in detected["sources"] if source.get("local_path") and
                  (brain_usage.is_inside(source["local_path"], folder) or brain_usage.is_inside(str(folder), Path(source["local_path"])))),
                 None)
    if other:
        return {**result, "code": "folder_already_connected", "existing": other, "commands": [],
                "summary": f"source {other['id']} already reads this folder (or the repo around it): nothing was added "
                           "so pages are not imported twice"}
    if not _is_git_checkout(root):
        return {**result, "code": "not_a_checkout", "commands": [],
                "summary": f"{root} is not a git checkout of the repo"}
    if not folder.is_dir() or not _has_committed_notes(root, knowledge_path):
        return {**result, "code": "no_notes_yet", "commands": commands,
                "summary": f"{knowledge_path} has no committed note yet at {root}: run connect again after the first "
                           "note is committed (gbrain imports committed files only)"}
    return {**result, "code": "ready", "commands": commands,
            "summary": f"ready to add source {source_id} reading {folder} (branch {result['checked_out_branch']}) and sync it"}


def _is_same_folder(path_text: str | None, folder: Path) -> bool:
    return bool(path_text) and brain_usage.is_inside(path_text, folder) and brain_usage.is_inside(str(folder), Path(path_text))


def _is_git_checkout(root: Path) -> bool:
    try:
        return run_git(root, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except (GitError, FileNotFoundError):
        return False


def apply(plan_result: dict, should_sync: bool) -> dict:
    """Run the planned add (ready) and sync (ready, already_connected); stops at the first failure"""
    code, source_id = plan_result["code"], plan_result["source_id"]
    steps = []
    if code == "ready":
        exit_code, output = brain_usage.run_gbrain("sources", "add", source_id, "--path", plan_result["source_path"], "--json")
        parsed = brain_usage.parse_json(output) or {}
        added = exit_code == 0 and parsed.get("source_id") == source_id
        steps.append({"step": "sources add", "ok": added, "state": parsed.get("state"), "error": None if added else
                      (parsed.get("code") or parsed.get("error") or f"exit {exit_code}")})
        if not added:
            return {"ok": False, "code": "add_failed", "steps": steps,
                    "summary": f"gbrain did not add {source_id}; nothing else was run"}
    if should_sync:
        exit_code, output = brain_usage.run_gbrain("sync", "--source", source_id, "--no-pull", "--json")
        parsed = brain_usage.parse_json(output) or {}
        synced = exit_code == 0 and parsed.get("outcome") in ("synced", "up_to_date", "resumable", None) and bool(parsed)
        steps.append({"step": "sync", "ok": synced, "outcome": parsed.get("outcome"), "added": parsed.get("added"),
                      "modified": parsed.get("modified"), "deleted": parsed.get("deleted")})
        if not synced:
            return {"ok": False, "code": "sync_failed", "steps": steps,
                    "summary": f"source {source_id} is registered but the sync did not finish: run gbrain sync --source "
                               f"{source_id} --no-pull and read its message"}
    return {"ok": True, "code": "connected", "steps": steps,
            "summary": f"source {source_id} reads {plan_result['source_path']}" + (" and is synced" if should_sync else "")}
