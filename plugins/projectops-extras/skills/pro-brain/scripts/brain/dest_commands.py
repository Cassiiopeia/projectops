"""brain_cli destination commands: write, doctor, and the destination part of setup and status (one resolver for all)
write fails fast per destination with the doctor code; one failing destination never blocks the others.
"""
from __future__ import annotations

from pathlib import Path

from . import brain_usage, doctor, note_file, resolver, user_config
from .adapters import adapter_for

DESTINATION_CHOICES = ("repo", "local", "remote", "install-guide")
WRITE_OUTCOME_OK = ("written", "updated", "unchanged", "via_source_sync")


def _is_inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


def cmd_write(args, context: dict) -> dict:
    """Same note(s) to every chosen destination: resolve > select > quick doctor gate > write > per-destination results"""
    resolved = resolver.resolve(context)
    context = {**context, "_resolved": resolved}
    chosen, error = resolver.select(resolved, args.to)
    if error:
        return {"ok": False, "code": "unknown_destination", "summary": error, "next": "brain_cli.py status (destinations)"}
    if not chosen:
        return {"ok": False, "code": "no_destination", "summary": "no write destination is configured for this repo",
                "next": "brain_cli.py setup (choose where notes are written)"}
    try:
        loaded = [note_file.load_note(path, context["project"], args.id if len(args.note) == 1 else None) for path in args.note]
    except note_file.NoteError as problem:
        return {"ok": False, "code": problem.code, "summary": problem.message, "next": "fix the note file, then write again"}
    repo_chosen = any(item["kind"] == "repo-files" for item in chosen)
    inside = [note["path"] for note in loaded if _is_inside(Path(note["path"]), context["root"])]
    if inside and not resolved["repo_notes"]["value"]:
        return {"ok": False, "code": "note_inside_repo",
                "summary": "notes are not kept in this repo (repo_notes is off), but the note file is inside it",
                "next": "write the note to a temp file outside the repo (for example in the system temp folder) and pass that path"}
    results = []
    for destination in chosen:
        results += _write_destination(destination, context, loaded)
    failed = [item for item in results if not item["ok"]]
    written_paths = [item["path"] for item in results if item.get("path") and item["outcome"] in ("written", "updated")]
    next_steps = []
    if written_paths:
        next_steps.append(f"stage {', '.join(written_paths)} and commit with pro-commit")
    elif repo_chosen and not failed:
        next_steps.append("commit the note with pro-commit if it is not committed yet")
    if not repo_chosen:
        next_steps.append("nothing to commit: delete the temp note file")
    if failed:
        next_steps.append("fix: " + " | ".join(f"{item['destination']}: {item.get('fix') or item['summary']}" for item in failed))
    code = "written" if not failed else ("partial" if len(failed) < len(results) else "failed")
    result = {"ok": not failed, "code": code, "results": results,
              "notes": [{key: note[key] for key in ("id", "slug", "title", "path")} for note in loaded],
              "summary": "; ".join(f"{item['destination']}: {item['outcome']}" for item in results),
              "next": "; ".join(next_steps) or None}
    if "repo" not in resolved["write_targets"]:
        result["backup_hint"] = _backup_hints(resolved, context)
    return result


def _write_destination(destination: dict, context: dict, loaded: list[dict]) -> list[dict]:
    """Doctor gate (quick) then write; any exception is this destination's failure only"""
    try:
        if destination["kind"] != "repo-files":
            report = doctor.diagnose_destination(destination, context, quick=True)
            if report["health"] == "unhealthy":
                return [{"destination": destination["id"], "kind": destination["kind"], "ok": False, "outcome": "failed",
                         "code": report["code"], "fix": report["fix"], "summary": f"doctor: {report['code']}",
                         "slug": note["slug"]} for note in loaded]
        return adapter_for(destination, context).write_many(loaded)
    except Exception as error:   # keep the other destinations going
        return [{"destination": destination["id"], "kind": destination["kind"], "ok": False, "outcome": "failed",
                 "code": "adapter_error", "summary": f"{type(error).__name__}", "fix": "brain_cli.py doctor; report with /pro-skill-bug"}
                for _ in loaded]


def _backup_hints(resolved: dict, context: dict) -> list[str]:
    hints = []
    for destination in resolved["destinations"]:
        if destination["is_write_target"] and destination["kind"] != "repo-files":
            hint = adapter_for(destination, context).backup_hint()
            if hint:
                hints.append(f"{destination['id']}: {hint}")
    return hints


def cmd_doctor(args, context: dict) -> dict:
    resolved = resolver.resolve(context)
    report = doctor.run_doctor(context, resolved, args.to, quick=args.quick)
    key = user_config.repo_key(context.get("remote"), context["root"])
    log = doctor.save_log(report, key)
    report["log"] = log
    report["resolved"] = summarize_resolved(resolved)
    if "repo" not in resolved["write_targets"] and resolved["write_targets"]:
        report["backup_hint"] = _backup_hints(resolved, context)
    return report


def summarize_resolved(resolved: dict) -> dict:
    """Effective config for status/doctor: destinations with origins, no URL userinfo, no secret"""
    fields = ("id", "kind", "scope", "role", "origin", "name", "mcp_url_shown", "url_origin", "token_cred",
              "token_cred_origin", "write", "path", "source_id")
    return {"schema": resolved["schema"], "user_config_state": resolved["user_config_state"],
            "repo_notes": resolved["repo_notes"], "sync_branch": resolved["sync_branch"],
            "write_targets": resolved["write_targets"], "legacy_mapping": resolved["legacy_mapping"] or None,
            "destinations": [{key: item[key] for key in fields if item.get(key) is not None} for item in resolved["destinations"]]}


def recommend_destinations(context: dict, resolved: dict) -> dict:
    """Recommended answer to 'Where should notes be written?' from detection (pressing yes works)"""
    detected = context.get("_detected") or brain_usage.detect_gbrain()
    current = list(resolved["write_targets"])
    reasons = []
    recommended = ["repo"] if resolved["repo_notes"]["value"] else []
    if detected.get("kind") == "local":
        recommended.append("local")
        reasons.append(f"a local gbrain ({(detected.get('engine') or {}).get('effective_engine')}) is ready on this machine")
    remotes = [item["id"] for item in resolved["destinations"] if item["kind"] == "gbrain-remote" and item["is_write_target"]]
    recommended += remotes
    if detected.get("kind") == "remote" and not remotes:
        reasons.append("this machine is a thin client of a remote gbrain: add it with --to remote:NAME --remote-url URL")
    if not recommended:
        recommended = ["repo"]
    if "repo" in recommended:
        reasons.append("repo files keep notes reviewable and backed up by git")
    if not detected.get("installed"):
        reasons.append("no gbrain here yet: repo files now, install-guide when you want a brain")
    return {"recommended": recommended, "current": current or ["repo"], "why": "; ".join(reasons),
            "choices": ["repo", "local", "remote:<name>", "team", "install-guide"]}


def destination_updates(args, context: dict, resolved: dict) -> dict:
    """setup flags > {switch_updates, switch_removals, personal (new entry or None), error}"""
    updates, removals, error = {}, [], None
    has_team = False
    wanted = [part.strip() for part in (args.to or "").split(",") if part.strip()]
    personal_current, _ = user_config.read_repo_entry(context.get("remote"), context["root"])
    set_local, add_remote, remove_remotes = None, None, []
    if args.remote_name or args.remote_url:
        add_remote = {"name": (args.remote_name or "").strip(), "mcp_url": (args.remote_url or "").strip(),
                      "token_cred": (args.remote_token_cred or args.remote_name or "").strip()}
        error = user_config.validate_remote(add_remote)
    if wanted:
        if "install-guide" in wanted and len(wanted) == 1:
            wanted = ["repo"]
        wanted = [name for name in wanted if name != "install-guide"]
        updates["repo_notes"] = "repo" in wanted
        set_local = "local" in wanted
        keep = {name.split(":", 1)[1].lower() for name in wanted if name.startswith(resolver.REMOTE_PREFIX)}
        if add_remote:
            keep.add(add_remote["name"].lower())
        remove_remotes = [item["name"] for item in personal_current["remotes"] if item["name"].lower() not in keep]
        unknown_remotes = keep - {item["name"].lower() for item in personal_current["remotes"]} - \
            ({add_remote["name"].lower()} if add_remote else set())
        if unknown_remotes and not error:
            error = f"remote {', '.join(sorted(unknown_remotes))} is not configured: pass --remote-name/--remote-url for it"
        has_team = any(item["id"] == "team" for item in resolved["destinations"]) or bool(args.team_brain_name)
        if "team" in wanted and not has_team and not error:
            error = "no shared team brain recorded: pass --team-brain-name (and --team-brain-url when the repo may show it)"
        if not any([updates["repo_notes"], set_local, keep, "team" in wanted]) and not error:
            error = "choose at least one destination (repo, local, team or remote:NAME)"
        # --to lists write destinations: team in it = write directly; left out = the team brain stays, read via sync
        if has_team and not args.team_write:
            updates["_team_write"] = "direct" if "team" in wanted else "sync"
    if args.team_write:
        updates["_team_write"] = args.team_write
    if args.sync_branch:
        updates["sync_branch"] = args.sync_branch.strip()
    if updates:
        updates["schema"] = resolver.REPO_SWITCH_SCHEMA
    personal = None
    if set_local is not None or add_remote or remove_remotes or args.team_token_cred:
        personal = user_config.plan_entry_update(personal_current, set_local, add_remote, remove_remotes, args.team_token_cred)
    return {"switch_updates": updates, "switch_removals": removals, "personal": personal,
            "personal_current": personal_current, "error": error}
