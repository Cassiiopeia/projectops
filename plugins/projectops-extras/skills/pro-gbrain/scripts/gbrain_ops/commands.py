"""Subcommands: detect, plan, add, repair, status, verify, share, remove. Each returns one JSON dict (ok, code, summary, next).
Writes happen only with --apply --yes (remove additionally needs --confirm <project>).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import common, context, flows, local_sync, mcp_check, provisioner as provisioner_module, registry_store

SHARE_FOLDER_NAME = "share"


class NeedsConsent(Exception):
    pass


def _facts(args) -> dict:
    facts = context.detect(Path(args.repo or ".").resolve(), getattr(args, "project", None))
    common.validate_project_key(facts["project"])
    return facts


def _open(section: dict | None):
    return provisioner_module.open_provisioner(section)


def _options(args) -> dict:
    return {key: getattr(args, key, None) for key in ("capture", "claude_md", "contact", "mcp_url", "mcp_name", "no_first_sync")}


def cmd_detect(args) -> dict:
    facts = context.detect(Path(args.repo or ".").resolve(), args.project)
    question = facts["question"]
    return {"ok": True, "code": "detected", **facts,
            "summary": f"project {facts['project']} ({facts['project_from']}); recommended: {question['recommended']} ({question['why']})",
            "next": f"ask the question once, then: plan --mode {question['recommended']}"}


def cmd_plan(args) -> dict:
    facts = _facts(args)
    section = registry_store.load_section()
    provisioner = _open(section) if args.mode == "team" else None
    run = flows.Run(facts, args.mode, _options(args), section, provisioner)
    steps = []
    for step_name in flows.STEPS_BY_MODE[args.mode]:
        recorded = run.state["steps"].get(step_name) or {}
        steps.append({"step": step_name, "recorded": recorded.get("status"), "does": _describe_step(run, step_name)})
    preview = None
    if args.mode == "team" and provisioner is not None:
        preview = provisioner.create(facts["project"], dry_run=True)
    repo_preview = flows.pro_brain.run_brain_cli(["setup"], run.repo_root)
    return {"ok": True, "code": "plan", "project": facts["project"], "mode": args.mode, "steps": steps,
            "server_preview": preview, "repo_preview": {key: repo_preview.get(key) for key in (
                "version_yml_diff", "block_diff", "target_options", "recommended_capture") if key in repo_preview},
            "summary": f"{len(steps)} steps for {facts['project']} ({args.mode})",
            "next": f"show the plan, ask once, then: add --mode {args.mode} --apply --yes"}


def _describe_step(run: flows.Run, step_name: str) -> str:
    project = run.project
    descriptions = {
        "server": (f"ask {run.provisioner.name} to create or adopt the team brain {project} (database, writer role, grants, "
                   "service, public route; re-running is safe)") if run.provisioner else
                  "no provisioner here: a brain admin creates the brain by hand (manual server steps), then pass --mcp-url/--mcp-name",
        "repo": "pro-brain setup in the repo: turn knowledge capture on, write the rule block"
                + (" and the shared team brain name and URL (never a token)" if run.mode == "team" else ""),
        "connect": "pro-brain connect: add one source <project>-knowledge to your own GBrain and sync it",
        "local": (f"{run.home_directory}: sparse clone of {run.facts['default_branch']} (knowledge/ + root files), gbrain config "
                  "for the writer role (600), source, sync.sh (700), first sync") if run.provisioner else "skipped (no provisioner)",
        "registry": f"add {registry_store.team_brain_name(project)} and projects.{project}.knowledge to the private registry "
                    "(backup first, existing values kept)",
        "verify": "throwaway read-only token: initialize 200, search, write refused, revoke, then 401",
    }
    return descriptions[step_name]


def _require_consent(args) -> None:
    if not (args.apply and args.yes):
        raise NeedsConsent("this command writes; show the plan and add --apply --yes after the user agreed")


def cmd_add(args) -> dict:
    _require_consent(args)
    facts = _facts(args)
    section = registry_store.load_section()
    provisioner = _open(section) if args.mode == "team" else None
    run = flows.Run(facts, args.mode, _options(args), section, provisioner)
    only_steps = [step.strip() for step in args.steps.split(",")] if args.steps else None
    result = flows.execute(run, redo_all=False, only_steps=only_steps)
    return _finish(result, run)


def cmd_repair(args) -> dict:
    _require_consent(args)
    facts = _facts(args)
    state = flows.load_state(facts["project"])
    mode = args.mode or state.get("mode")
    if not mode:
        return {"ok": False, "code": "nothing_to_repair", "summary": f"no recorded setup for {facts['project']}",
                "next": "run detect, then add"}
    section = registry_store.load_section()
    provisioner = _open(section) if mode == "team" else None
    run = flows.Run(facts, mode, _options(args), section, provisioner)
    only_steps = [step.strip() for step in args.steps.split(",")] if args.steps else None
    return _finish(flows.execute(run, redo_all=True, only_steps=only_steps), run)


def _finish(result: dict, run: flows.Run) -> dict:
    result.update({"project": run.project, "mode": run.mode, "state_file": str(flows.state_path(run.project))})
    if result["ok"]:
        result["summary"] = f"{run.project}: {', '.join(result['finished']) or 'nothing new'} done ({run.mode})"
        result["next"] = (f"commit the repo changes with pro-commit; teammates: share --project {run.project} --member <name>"
                          if run.mode == "team" else "commit the repo changes with pro-commit")
    return result


def cmd_verify(args) -> dict:
    project = common.validate_project_key(args.project)
    section = registry_store.load_section()
    provisioner = _open(section)
    if provisioner is None:
        return {"ok": False, "code": "no_provisioner", "summary": "no brain server token API configured",
                "next": "verify by hand with a teammate token: pro-brain connect --team"}
    brain = registry_store.brains(section).get(registry_store.team_brain_name(project)) or {}
    verification = mcp_check.run_verification(provisioner, project, brain.get("mcp_url"))
    return {"ok": verification["passed"], "code": "verified" if verification["passed"] else "verify_failed",
            "summary": f"{project}: end-to-end check {'passed' if verification['passed'] else 'failed'}", **verification}


def cmd_status(args) -> dict:
    section = registry_store.load_section()
    rows = registry_store.describe_brain_entries(section)
    server_rows, server_error = {}, None
    try:
        provisioner = _open(section)
        if provisioner is not None:
            server_rows = {brain.get("project"): brain for brain in provisioner.list_brains()}
    except common.StepError as error:
        server_error = {"code": error.code, "summary": error.message}
    projects = (section or {}).get("projects") or {}
    sync_root = common.default_sync_root()
    seen = set()
    for row in rows:
        project = row["name"].removesuffix(registry_store.TEAM_BRAIN_SUFFIX)
        seen.add(project)
        _fill_row(row, project, projects, server_rows, sync_root)
    for project, server in server_rows.items():
        if project and project not in seen:
            row = {"name": registry_store.team_brain_name(project), "in_registry": False}
            _fill_row(row, project, projects, server_rows, sync_root)
            rows.append(row)
    if args.project:
        rows = [row for row in rows if row["project"] == args.project]
    return {"ok": True, "code": "status", "brains": rows, "server_error": server_error,
            "summary": f"{len(rows)} team brain(s)" + (f"; server not reachable ({server_error['code']})" if server_error else ""),
            "next": "repair --project <key> --apply --yes for a broken one"}


def _fill_row(row: dict, project: str, projects: dict, server_rows: dict, sync_root: Path) -> None:
    server = server_rows.get(project) or {}
    knowledge = (projects.get(project) or {}).get("knowledge") or {}
    row.update({"project": project, "switch_in_registry": knowledge.get("enabled"),
                "server": {key: server.get(key) for key in ("service_state", "is_healthy", "port", "version")} if server else None,
                "this_machine": local_sync.describe(sync_root / project)})


def cmd_share(args) -> dict:
    project = common.validate_project_key(args.project)
    section = registry_store.load_section()
    provisioner = _open(section)
    if provisioner is None:
        return {"ok": False, "code": "no_provisioner", "summary": "no brain server token API configured",
                "next": "the brain admin issues a read-only token with the brain's admin tools"}
    member = (args.member or "").strip()
    if not member:
        return {"ok": False, "code": "member_required", "summary": "who is the token for?", "next": "share --member <name>"}
    if not (args.apply and args.yes):
        return {"ok": True, "code": "plan", "summary": f"issue one read-only token for {member} on {project}",
                "next": f"share --project {project} --member {member} --apply --yes"}
    issued = provisioner.issue_read_only_token(project, to_token_label(member))
    message_path = _write_share_message(project, member, issued)
    copied = _copy_to_clipboard(message_path)
    return {"ok": True, "code": "shared", "token_id": issued.get("token_id"), "scopes": issued.get("scopes"),
            "message_file": str(message_path), "copied_to_clipboard": copied,
            "summary": f"read-only token for {member} saved in a private file (600); the token is not shown here",
            "next": "send the file's text to the member one to one (DM), then delete the file"}


def to_token_label(member: str) -> str:
    """Teammate name > token label the reference server accepts (lower case letters, digits, hyphens; 2-63 chars)"""
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", member.lower()).strip("-")[:40] or "member"
    return f"{slug}-{common.compact_timestamp()}"


def _write_share_message(project: str, member: str, issued: dict) -> Path:
    name = issued.get("mcp_server_name") or f"gbrain-{project}"
    lines = [
        f"{member}, here is your read-only access to the {project} team brain.",
        "",
        "1. Install the projectops-extras plugin if you do not have it:",
        "   claude plugin install projectops-extras@projectops-marketplace --scope user",
        "2. In a terminal, store the token (hidden input; paste the token below when asked):",
        f"   python3 ~/.projectops/bin/projectops_cli.py launch cred set --name {name} --secret-field token --prompt",
        f"   token: {issued.get('secret')}",
        "3. Open the project repo in Claude Code and say: /pro-brain connect the team brain",
        f"   (it adds the MCP server {name} -> {issued.get('mcp_url')} for your user only; restart the session after)",
        "",
        "Keep the token to yourself; ask for a new one if it leaks.",
    ]
    path = common.state_directory() / SHARE_FOLDER_NAME / f"{project}-{member}-{common.compact_timestamp()}.txt"
    common.ensure_private_directory(path.parent)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(common.PRIVATE_FILE_MODE)
    return path


def _copy_to_clipboard(path: Path) -> bool:
    for tool in (["pbcopy"], ["clip"], ["xclip", "-selection", "clipboard"], ["wl-copy"]):
        if shutil.which(tool[0]):
            import subprocess
            try:
                subprocess.run(tool, input=path.read_text(encoding="utf-8"), encoding="utf-8", errors="replace", check=True, timeout=10)
                return True
            except (subprocess.SubprocessError, OSError):
                return False
    return False


def cmd_remove(args) -> dict:
    """Detach only: disable this machine's sync script and flag the registry entry. Never deletes data"""
    project = common.validate_project_key(args.project)
    home_directory = common.default_sync_root() / project
    plan = {"disable_sync_script": str(home_directory / local_sync.SYNC_SCRIPT_NAME),
            "flag_registry_entry": registry_store.team_brain_name(project),
            "kept": ["the server brain, database and service", "the clone and gbrain config on this machine",
                     "repo notes and the repo switch (turn the team brain off with pro-brain setup --team-brain-off)"],
            "server_removal": "not automated: the brain admin removes the service and database by hand if wanted"}
    if not args.apply:
        return {"ok": True, "code": "plan", **plan, "summary": f"detach {project} (no data is deleted)",
                "next": f"ask the user to type the project key, then: remove --project {project} --apply --confirm {project}"}
    if args.confirm != project:
        return {"ok": False, "code": "confirmation_mismatch", "summary": "the typed confirmation does not match the project key",
                "next": f"remove --project {project} --apply --confirm {project}"}
    script = home_directory / local_sync.SYNC_SCRIPT_NAME
    disabled = None
    if script.exists():
        disabled = script.with_name(f"{local_sync.SYNC_SCRIPT_NAME}.disabled-{common.compact_timestamp()}")
        script.rename(disabled)
    registry_result = registry_store.mark_removed(project)
    return {"ok": True, "code": "removed", "sync_script_disabled_as": str(disabled) if disabled else None,
            "registry": registry_result, "kept": plan["kept"],
            "summary": f"{project} detached on this machine; nothing was deleted", "next": None}
