"""brain_cli connect and install: personal GBrain source, team brain MCP entry, guided install
Same resolver as write and doctor: the team brain's URL and token name come from resolver.resolve.
"""
from __future__ import annotations

from . import brain_usage, gbrain_connect, install_guide, mcp_probe, resolver, team_connect
from .commands import NeedsConsent, repo_context


def cmd_connect(args) -> dict:
    """Personal GBrain: plan (default) or --apply --yes to add the source and sync it; --team: the team brain MCP entry"""
    context = repo_context(args.repo)
    if args.team:
        return _connect_team(args, context)
    knowledge_path = context["switch"].get("path", "knowledge/")
    result = gbrain_connect.plan(context["root"], knowledge_path, context["project"], context["default_branch"],
                                 args.source_id, args.source_root, is_remote=args.remote)
    code = result["code"]
    next_by_code = {
        "ready": "show the source id, path and branch, then connect --apply --yes after the user agreed",
        "already_connected": "connect --apply --yes syncs it again (no add)",
        "source_id_taken": "stop and report; ask for another id (connect --source-id NAME), never overwrite",
        "folder_already_connected": "stop and report the existing source; nothing to add",
        "no_notes_yet": "write and commit the first note, then run connect again",
        "remote_brain": "give the user the commands to run on the brain host; do not change MCP settings",
        "brain_not_initialized": "the user creates a brain first (gbrain init), or keep repo-only",
        "gbrain_missing": f"show the install guide ({brain_usage.GBRAIN_INSTALL_URL}) and keep repo-only",
    }
    if not args.apply:
        return {**result, "next": next_by_code.get(code, "report the summary")}
    if code not in ("ready", "already_connected"):
        return {**result, "ok": False, "summary": f"nothing applied: {result['summary']}", "next": next_by_code.get(code)}
    if not args.yes:
        raise NeedsConsent("connect --apply adds a source to the user's GBrain: pass --yes only after the user agreed")
    outcome = gbrain_connect.apply(result, should_sync=not args.no_sync)
    return {**result, **outcome,
            "next": ("one line to the user: notes enter the brain from the branch checked out at the source path; "
                     "for merged notes only, follow default_branch_recipe" if outcome["ok"] else "report the failed step")}


def _connect_team(args, context: dict) -> dict:
    """Team brain: plan (default) or --apply --yes to register the user-scope MCP entry with the stored token"""
    # Same chain as write and doctor: switch > registry URL fallback (name-only public repos) > token name
    team_destination = next((item for item in resolver.resolve(context)["destinations"] if item["id"] == resolver.DESTINATION_TEAM), None)
    team = None
    if team_destination:
        team = {"mcp_name": team_destination["name"], "mcp_url": team_destination.get("mcp_url") or ""}
        if team_destination.get("contact"):
            team["contact"] = team_destination["contact"]
    result = team_connect.plan(team, args.token_cred or (team_destination or {}).get("token_cred"), context["project"],
                               context["root"], args.rotate, args.project_mcp_json)
    if team and team.get("mcp_url") and not args.no_probe and result["code"] not in ("bad_team_brain",):
        result["team_brain_probe"] = mcp_probe.probe_team_brain(team["mcp_url"], team.get("mcp_name"), context["project"])
    code = result["code"]
    next_by_code = {
        "ready": "show the command (token placeholder) and the probe verdict, then connect --team --apply --yes after a yes",
        "already_registered": "nothing to do; after a token change: store the new token, then connect --team --rotate",
        "token_missing": "the user runs store_token_command in their own terminal (hidden input needs a TTY; the ! prefix "
                         "in Claude Code has none), or saves the token to a file and you run store_token_without_tty; "
                         "then connect --team again",
        "claude_cli_missing": "give the user the command; they put their token in place of <token> in their own terminal",
        "no_team_brain": "setup --team-brain-name N --team-brain-url URL --team-brain-contact WHO (ask the user first)",
        "bad_team_brain": "fix team_brain in version.yml with setup --team-brain-* flags",
        "no_team_brain_url": "ask the brain admin for the URL; add it to your registry or setup --team-brain-url URL",
        "config_unreadable": "the user repairs ~/.projectops/config/config.json first",
    }
    project_note = ""
    if args.project_mcp_json and result.get("project_mcp_json"):
        project_note = (f"; .mcp.json reads ${{{result['project_mcp_json'].get('env_var')}}}: each teammate sets that "
                        "variable, and a project entry overrides a user entry of the same name")
    if not args.apply:
        return {**result, "next": next_by_code.get(code, "report the summary") + project_note}
    if not args.yes:
        raise NeedsConsent("connect --team --apply registers an MCP entry with the user's token: pass --yes only after the user agreed")
    outcome = team_connect.apply(result, context["root"], context["project"])
    # Closing loop: after the restart, doctor proves the entry answers and (direct mode) that the key can write
    after_restart = "brain_cli.py doctor --to team"
    return {**result, **outcome, "after_restart": after_restart if outcome["ok"] else None,
            "next": (f"restart the agent session so the MCP entry loads, then run {after_restart}; commit .mcp.json with "
                     "pro-commit if it was written" if outcome["ok"] else next_by_code.get(code, "report the failed step"))}


def cmd_install(args) -> dict:
    """Guided install and init: one question, then exact commands, prerequisites and verification (read only)"""
    return install_guide.guide(args.choice)
