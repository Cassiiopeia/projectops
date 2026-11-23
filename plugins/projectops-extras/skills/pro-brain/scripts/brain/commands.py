"""brain_cli subcommands: parse input > call module > result + next (status, collect, setup, gaps)
Read-only except setup --apply --yes, which the agent runs only after the user agreed.
"""
from __future__ import annotations

import difflib
from pathlib import Path

from . import (brain_usage, collect, contracts, gaps, gbrain_connect, install_guide, mcp_probe, notes, onboarding, registry,
               repo_facts, switch_edit, team_connect)

DEFAULT_CAPTURE = "issue-end"   # repos switched on before capture modes existed keep the issue flow
TEAM_BRAIN_DECLINED = "none"    # team_brain value when the user chose no team brain


class NeedsConsent(Exception):
    pass


def repo_context(repo_argument: str | None) -> dict:
    """Repo root, remote, version.yml facts, repo switch, private registry match and team brain MCP name"""
    root = repo_facts.find_repo_root(Path(repo_argument or ".").resolve())
    if root is None:
        raise LookupError("not inside a git repository")
    remote = repo_facts.read_remote_slug(root)
    section = registry.load_section()
    project_key, entry = registry.find_project(section, remote, root) if section else (None, None)
    text = repo_facts.read_version_yml_text(root)
    facts = repo_facts.read_version_facts(text)
    switch = repo_facts.read_knowledge_switch(text)
    sync_target = registry.describe_sync_target(section, project_key, entry)
    default_branch = facts["default_branch"] or "main"
    return {"root": root, "remote": remote, "section": section, "project_key": project_key, "entry": entry or {},
            "text": text, "facts": facts, "switch": switch, "sync_target": sync_target,
            "default_branch": default_branch, "language": repo_facts.read_repo_language(text),
            # Only the shared repo switch feeds the rule block; the owner's registry is a hint for the setup question
            "brain_mcp": repo_facts.team_brain_mcp_name(switch),
            "registry_mcp_hint": sync_target.get("mcp_server_name") if sync_target.get("known") else None,
            "registry_token_cred": sync_target.get("token_cred") if sync_target.get("known") else None,
            "project": project_key or (remote or root.name).split("/")[-1].lower()}


def default_ref(root: Path, default_branch: str) -> str:
    for ref in (f"origin/{default_branch}", default_branch):
        try:
            repo_facts.run_git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
            return ref
        except repo_facts.GitError:
            continue
    return "HEAD"


def _onboarding_facts(context: dict, capture: str) -> dict:
    """Which onboarding questions are still open: capture mode, rule block (unless declined), block refresh"""
    root, switch = context["root"], context["switch"]
    block = onboarding.render_block(context["language"], capture, switch.get("path", "knowledge/"),
                                    context["default_branch"], context["brain_mcp"], switch.get("rules"))
    files = onboarding.instruction_files(root)
    decision = switch.get("claude_md")
    target = decision if decision and decision != "declined" else onboarding.target_options(files)[0]["target"]
    state = "declined" if decision == "declined" else onboarding.block_state(root / target, block)
    # The owner's registry names a team brain the shared switch lacks: ask before the block loses or gains a lookup line
    has_unshared_team_brain = (bool(context.get("registry_mcp_hint")) and not context.get("brain_mcp")
                               and not switch.get("team_brain_declined"))
    open_questions = [name for name, is_open in (("capture", not switch.get("capture")),
                                                 ("rule_block", state == "absent"),
                                                 ("usage", has_unshared_team_brain)) if is_open]
    return {"open_questions": open_questions, "rule_block_target": target, "rule_block_state": state,
            "claude_md": files["claude_md"], "claude_md_state": files["claude_md_state"]}


def cmd_status(args) -> dict:
    context = repo_context(args.repo)
    switch, sync_target = context["switch"], context["sync_target"]
    result = {"repo_root": str(context["root"]), "remote": context["remote"], "project_key": context["project_key"],
              "switch": switch, "sync_target": sync_target, "brain_mcp": context["brain_mcp"]}
    if not switch["enabled"]:
        intent = sync_target.get("registry_intent", {}) if sync_target.get("known") else {}
        hint = " The private registry wants it on." if intent.get("enabled") else ""
        return {**result, "code": "switch_off",
                "summary": "knowledge capture is off for this repo (version.yml metadata.template.options.knowledge.enabled is not true)." + hint,
                "next": "reached through a pointer: stop with one line. Asked directly (or the registry wants it on): "
                        "run setup to show the onboarding questions, then setup --apply --yes --enable after the user agrees"}
    capture = switch.get("capture") or DEFAULT_CAPTURE
    folder = context["root"] / switch["path"]
    result.update({"capture": capture, "knowledge_folder_exists": folder.is_dir(),
                   "onboarding": _onboarding_facts(context, capture)})
    # rules is relative to the repo root; template is relative to the knowledge folder
    if "rules" in switch:
        result["rules_exists"] = (context["root"] / str(switch["rules"])).is_file()
    if "template" in switch:
        result["template_exists"] = (folder / str(switch["template"])).is_file()
    sync_line = (f"synced by brain '{sync_target['brain']}' as source '{sync_target['source_id']}'" if sync_target["known"]
                 else f"no sync target known on this machine ({sync_target['reason']}); the note is still written")
    onboarding_state = result["onboarding"]
    if onboarding_state["open_questions"]:
        next_step = f"onboarding open ({', '.join(onboarding_state['open_questions'])}): run setup, ask its questions, then setup --apply --yes"
    elif onboarding_state["rule_block_state"] == "outdated":
        next_step = "rule block is outdated: refresh it in place with setup --apply --yes --claude-md add (consent already given), then go on"
    else:
        next_step = "judge whether this work produced durable knowledge; if yes run collect, if not skip with a one-line reason"
    return {**result, "code": "switch_on", "summary": f"knowledge capture is on ({capture}): notes go to {switch['path']}; {sync_line}",
            "next": next_step}


def _deploy_targets(raw: str | None) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def cmd_collect(args) -> dict:
    context = repo_context(args.repo)
    root, switch, facts = context["root"], context["switch"], context["facts"]
    capture = args.capture_mode or switch.get("capture") or DEFAULT_CAPTURE
    is_change_set = args.change_set or bool(args.commits) or (capture != "issue-end" and not args.issue)
    branch = args.branch or repo_facts.current_branch(root)
    issue = args.issue or (None if is_change_set else collect.issue_from_branch(branch))
    knowledge_path = switch.get("path", "knowledge/")
    existing = notes.scan_notes(root / knowledge_path, context["remote"])
    head_sha = repo_facts.run_git(root, "rev-parse", args.head or "HEAD").strip()
    commit_range = collect.resolve_range(
        root, args.base, args.head, issue, branch, facts["development_branch"], context["default_branch"],
        commits=[sha.strip() for sha in (args.commits or "").split(",") if sha.strip()] or None,
        last_captured_head=notes.last_captured_head(root, existing, head_sha) if is_change_set else None)
    # Version and build number as of the last commit of the range, not today's working tree
    head_facts = repo_facts.read_version_facts(repo_facts.read_version_yml_text(root, commit_range["head"]))
    # The checked-out branch belongs to the note only in branch mode; otherwise record it only when passed
    if commit_range["mode"] != "branch" and not args.branch:
        branch = None
    registry_repo = registry.matching_repo(context["entry"], context["remote"]) if context["entry"] else {}
    files = collect.changed_files(root, commit_range, knowledge_path)
    changes = collect.summarize_changes(files, collect.stack_paths(registry_repo, head_facts))
    contract_changes = contracts.detect_contract_changes(root, commit_range, list(files), knowledge_path)
    merge_targets = [f"origin/{context['default_branch']}", context["default_branch"]]
    if facts["development_branch"]:
        merge_targets += [f"origin/{facts['development_branch']}", facts["development_branch"]]
    merge_commit = args.merge_commit or (collect.find_merge_commit(root, commit_range["head"], merge_targets)
                                         if commit_range["mode"] != "since-last-note" else None)
    deploy_targets = _deploy_targets(args.deploy_target)
    captured = collect.now_seoul()
    metadata = {
        "capture_mode": capture, "captured_at": captured.isoformat(timespec="seconds"), "captured_by": "pro-brain",
        "project": context["project"], "stacks": changes["stacks"],
        "app_version": head_facts["version"], "build_number": head_facts["version_code"],
        "issue": issue,
        "issue_url": f"https://github.com/{context['remote']}/issues/{issue}" if issue and context["remote"] else None,
        "pr": args.pr_number, "pr_url": args.pr_url, "branch": branch,
        "commit_base": commit_range["base"], "commit_head": commit_range["head"], "commit_count": len(commit_range["commits"]),
        "commits": [sha[:9] for sha in commit_range["commits"]] if commit_range["mode"] == "commit-list" else None,
        "merge_commit": merge_commit,
        "changed_modules": changes["changed_modules"], "main_files": changes["main_files"],
        "lines_added": changes["lines_added"], "lines_deleted": changes["lines_deleted"],
        **contract_changes,
        "deployed": True if deploy_targets else None, "deploy_targets": deploy_targets, "deploy_version": args.deploy_version,
    }
    created = captured.date().isoformat()
    hints = collect.topic_hints(changes, contract_changes)
    identity = collect.suggest_note_identity(issue, commit_range, created, args.title_hint)
    suggested = {**identity, "note_dir": switch.get("note_dir") or ("issues/" if issue else "changes/"),
                 "topic_hints": hints, "existing_topics": notes.existing_topics(existing),
                 "related": notes.related_notes(existing, changes["changed_modules"], changes["main_files"], hints)}
    missing = [name for name, value in (("pr", args.pr_number), ("branch", branch)) if not value]
    result = {
        "kind": "change-set" if is_change_set else "issue", "range_mode": commit_range["mode"], "created": created,
        "changed_file_count": changes["changed_file_count"], "metadata": metadata,
        "frontmatter": "\n".join(collect.frontmatter_lines(metadata)), "suggested": suggested, "switch": switch,
        "summary": f"{len(commit_range['commits'])} commit(s), {changes['changed_file_count']} file(s), "
                   f"+{changes['lines_added']}/-{changes['lines_deleted']}, stacks {', '.join(changes['stacks']) or 'none'}",
        "next": ("write the note (references/note-format.md): repo rules/template first, these keys appended to its frontmatter"
                 + (f"; not given: {', '.join(missing)} (pass --pr-number/--pr-url/--branch when they exist)" if missing else "")),
    }
    if is_change_set:
        result["commit_outline"] = collect.commit_outline(root, commit_range)
        result["next"] += "; group commit_outline by topic and run collect --commits a,b,c per topic when it mixes topics"
    return result


def _usage_facts(context: dict) -> dict:
    """How the repo's knowledge is read now and what to recommend (question 3 of onboarding)"""
    detected = brain_usage.detect_gbrain()
    switch = context["switch"]
    team = switch.get("team_brain") if isinstance(switch.get("team_brain"), dict) else None
    team = team or ({"mcp_name": switch["brain_mcp"]} if switch.get("brain_mcp") else None)
    source_id = gbrain_connect.default_source_id(context["project"])
    connected = brain_usage.personal_sources_for_repo(detected, context["root"], source_id)
    registry_hint = None if switch.get("team_brain_declined") or switch.get("team_brain") == TEAM_BRAIN_DECLINED else context["registry_mcp_hint"]
    recommendation = brain_usage.recommend_usage(detected, team, registry_hint, connected)
    facts = {"current": brain_usage.current_usage(detected, team, connected), "recommended": recommendation["modes"],
             "why": recommendation["reason"], "choices": list(brain_usage.USAGE_MODES),
             "gbrain": {key: detected.get(key) for key in ("installed", "kind", "brain_ready", "engine")},
             "personal_sources": connected, "source_id": source_id, "team_brain": team,
             "registry_mcp_hint": context["registry_mcp_hint"], "install_url": brain_usage.GBRAIN_INSTALL_URL}
    if team and team.get("mcp_url"):
        facts["team_brain_setup"] = brain_usage.team_brain_instructions(team, brain_usage.claude_mcp_server_names(),
                                                                        context.get("registry_token_cred"))
    return facts


def _setup_questions(context: dict, recommendation: dict, onboarding_state: dict, options: list[dict],
                     usage: dict) -> list[dict]:
    """At most three questions, each with a recommended answer so 'yes' is enough"""
    questions = []
    if "capture" in onboarding_state["open_questions"] or not context["switch"]["enabled"]:
        questions.append({"id": "capture", "recommended": recommendation["mode"], "why": recommendation["reason"],
                          "question": f"When should knowledge notes be written? Recommended: {recommendation['mode']}",
                          "choices": list(repo_facts.CAPTURE_MODES)})
    if onboarding_state["rule_block_state"] == "absent":
        target = options[0]
        place = ("the project CLAUDE.md" if target["kind"] == "tracked-claude-md" else f"{target['target']} ({target['why']})")
        questions.append({"id": "rule_block", "recommended": "add", "target": target["target"],
                          "question": f"May I add the knowledge rule to {place}? (recommended)",
                          "choices": ["add", "decline"] + [option["target"] for option in options[1:]]})
    # Always asked in setup: re-running onboarding shows the current state and lets the user change it
    questions.append({"id": "usage", "recommended": usage["recommended"], "current": usage["current"], "why": usage["why"],
                      "question": "How do you use this repo's knowledge? (a personal GBrain can be combined with a team brain)",
                      "choices": usage["choices"], "multi_select": True})
    return questions


def _team_brain_updates(args, switch: dict) -> tuple[dict, tuple[str, ...], str | None]:
    """--team-brain-* flags > (switch updates, keys to remove, error); off records team_brain: "none" (never asked again)"""
    if args.team_brain_off:
        return {"team_brain": TEAM_BRAIN_DECLINED}, ("brain_mcp",), None
    if not (args.team_brain_name or args.team_brain_url or args.team_brain_contact):
        return {}, (), None
    current = dict(switch.get("team_brain") or {}) if isinstance(switch.get("team_brain"), dict) else {}
    if switch.get("brain_mcp") and "mcp_name" not in current:
        current["mcp_name"] = switch["brain_mcp"]
    for key, value in (("mcp_name", args.team_brain_name), ("mcp_url", args.team_brain_url),
                       ("contact", args.team_brain_contact)):
        if value:
            current[key] = value.strip()
    error = brain_usage.validate_team_brain(current)
    # team_brain.mcp_name replaces the legacy brain_mcp key
    return {"team_brain": current}, ("brain_mcp",) if switch.get("brain_mcp") else (), error


def cmd_setup(args) -> dict:
    context = repo_context(args.repo)
    root, switch = context["root"], context["switch"]
    recommendation = onboarding.recommend_capture(root, default_ref(root, context["default_branch"]), context["remote"])
    capture = args.capture or switch.get("capture") or recommendation["mode"]
    team_updates, team_removals, team_error = _team_brain_updates(args, switch)
    if team_error:
        return {"ok": False, "code": "bad_team_brain", "summary": team_error,
                "next": "fix the --team-brain-* values (name like gbrain-<project>, an https URL without a token)"}
    brain_mcp = (None if args.team_brain_off else
                 (team_updates.get("team_brain") or {}).get("mcp_name") or args.brain_mcp or context["brain_mcp"])
    knowledge_path = switch.get("path", "knowledge/")
    block = onboarding.render_block(context["language"], capture, knowledge_path, context["default_branch"], brain_mcp,
                                    switch.get("rules") or onboarding.detect_rules_file(root))
    files = onboarding.instruction_files(root)
    options = onboarding.target_options(files)
    recorded = switch.get("claude_md") if switch.get("claude_md") not in (None, "declined") else None
    target = args.target or recorded or options[0]["target"]
    target_kind = next((option["kind"] for option in options if option["target"] == target), "custom")
    onboarding_state = _onboarding_facts({**context, "brain_mcp": brain_mcp}, capture) if switch["enabled"] else \
        {"open_questions": ["capture", "rule_block"], "rule_block_state": onboarding.block_state(root / target, block)}
    if switch.get("claude_md") == "declined" and not args.claude_md:
        onboarding_state["rule_block_state"] = "declined"
    updates = {}
    if args.capture or not switch.get("capture"):
        updates["capture"] = capture
    if args.claude_md == "add":
        updates["claude_md"] = target
    elif args.claude_md == "decline":
        updates["claude_md"] = "declined"
    if args.brain_mcp and not team_updates and not args.team_brain_off:
        updates["brain_mcp"] = args.brain_mcp
    updates.update(team_updates)
    detected_rules = onboarding.detect_rules_file(root) if not switch.get("rules") else None
    if detected_rules:
        updates["rules"] = detected_rules   # the repo's own vault rules win over the default note format
    # Turning on is part of onboarding when the switch is off: the plan previews it, apply needs --enable
    needs_enable = not switch["enabled"]
    if args.enable or (needs_enable and not args.apply):
        updates["enabled"] = True
    try:
        new_version_text = (switch_edit.set_knowledge_keys(context["text"], updates, create_if_missing="enabled" in updates,
                                                           removals=team_removals)
                            if updates or team_removals else context["text"])
        switch_error = None
    except switch_edit.SwitchEditError as error:
        new_version_text, switch_error = context["text"], str(error)
    usage = _usage_facts({**context, "switch": {key: value for key, value in {**switch, **team_updates}.items()
                                                 if key not in team_removals}})
    # A new team brain URL is probed before it is shared, so a mistyped brain key shows up now (warning only)
    new_team = team_updates.get("team_brain") if isinstance(team_updates.get("team_brain"), dict) else None
    probe = (mcp_probe.probe_team_brain(new_team["mcp_url"], new_team.get("mcp_name"), context["project"])
             if new_team and args.team_brain_url and not args.no_probe else None)
    plan = {"recommended_capture": recommendation, "capture": capture, "brain_mcp": brain_mcp, "usage": usage, "files": files,
            "team_brain_probe": probe,
            "target_options": options, "target": target, "target_kind": target_kind, "block": block,
            "block_state": onboarding_state["rule_block_state"],
            "questions": _setup_questions(context, recommendation, onboarding_state, options, usage),
            "switch_updates": updates, "switch_error": switch_error,
            "version_yml_diff": "".join(difflib.unified_diff(
                context["text"].splitlines(keepends=True), new_version_text.splitlines(keepends=True),
                fromfile="a/version.yml", tofile="b/version.yml", n=1)),
            "block_diff": onboarding.preview_diff(root / target, target, block)}
    if not args.apply:
        return {**plan, "code": "plan", "summary": f"{len(plan['questions'])} question(s); recommended capture {recommendation['mode']}, "
                f"rule block target {target} ({target_kind})",
                "next": "ask the questions (recommended answer first, in the user's language), then "
                        f"setup --apply --yes{' --enable' if needs_enable else ''} --capture MODE --claude-md add|decline [--target PATH] "
                        "[--team-brain-name N --team-brain-url URL --team-brain-contact WHO | --team-brain-off]; "
                        "for local-gbrain or remote-gbrain run connect (plan) next; for install-guide show usage.install_url"}
    if needs_enable and not args.enable:
        raise NeedsConsent("capture is off for this repo: pass --enable together with --apply --yes once the user agreed to turn it on")
    if not args.yes:
        raise NeedsConsent("setup --apply writes version.yml and the rule block: pass --yes only after the user agreed")
    if switch_error:
        return {**plan, "ok": False, "code": "switch_edit_failed", "summary": switch_error,
                "next": "edit the knowledge block in version.yml by hand (references/note-format.md §Repo switch)"}
    written = []
    if new_version_text != context["text"]:
        (root / "version.yml").write_text(new_version_text, encoding="utf-8")
        written.append("version.yml")
    # A team brain change rewrites the block's lookup line, so a block that is already there follows it
    block_follows_switch = (team_updates or args.team_brain_off) and onboarding_state["rule_block_state"] not in ("absent", "declined")
    if args.claude_md == "add" or (args.claude_md is None and (onboarding_state["rule_block_state"] == "outdated" or block_follows_switch)):
        outcome = onboarding.apply_block(root / target, block)
        written.append(f"{target} ({outcome})")
        if args.agents_md and files["agents_md_needs_block"]:
            written.append(f"AGENTS.md ({onboarding.apply_block(root / 'AGENTS.md', block)})")
    follow_up = ["commit the tracked files above with pro-commit (stage only these paths)"]
    if probe and not probe["ok"]:
        follow_up.insert(0, f"warn the user: team brain URL probe said {probe['verdict']} ({probe['summary']})")
    if usage.get("team_brain_setup") and not usage["team_brain_setup"].get("registered"):
        follow_up.append("show usage.team_brain_setup.steps to the user (token from the contact, never stored)")
    if target_kind == "local-claude-md+worktree-copy" and args.claude_md == "add":
        follow_up.insert(0, f"python3 ~/.projectops/bin/projectops_cli.py init-worktree record --root {root} --copied {target}")
    return {**plan, "code": "applied", "written": written, "summary": f"wrote {', '.join(written) or 'nothing'}",
            "next": "; then ".join(follow_up)}


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
    switch = context["switch"]
    team = switch.get("team_brain") if isinstance(switch.get("team_brain"), dict) else None
    result = team_connect.plan(team, args.token_cred or context.get("registry_token_cred"), context["project"],
                               context["root"], args.rotate, args.project_mcp_json)
    if team and team.get("mcp_url") and not args.no_probe and result["code"] not in ("bad_team_brain",):
        result["team_brain_probe"] = mcp_probe.probe_team_brain(team["mcp_url"], team.get("mcp_name"), context["project"])
    code = result["code"]
    next_by_code = {
        "ready": "show the command (token placeholder) and the probe verdict, then connect --team --apply --yes after a yes",
        "already_registered": "nothing to do; after a token change: store the new token, then connect --team --rotate",
        "token_missing": "the user runs store_token_command in a terminal (! prefix in Claude Code), then connect --team again",
        "claude_cli_missing": "give the user the command; they put their token in place of <token> in their own terminal",
        "no_team_brain": "setup --team-brain-name N --team-brain-url URL --team-brain-contact WHO (ask the user first)",
        "bad_team_brain": "fix team_brain in version.yml with setup --team-brain-* flags",
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
    return {**result, **outcome,
            "next": ("restart the agent session so the MCP entry loads; commit .mcp.json with pro-commit if it was written"
                     if outcome["ok"] else next_by_code.get(code, "report the failed step"))}


def cmd_install(args) -> dict:
    """Guided install and init: one question, then exact commands, prerequisites and verification (read only)"""
    return install_guide.guide(args.choice)


def cmd_gaps(args) -> dict:
    context = repo_context(args.repo)
    switch = context["switch"]
    capture = args.capture or switch.get("capture") or DEFAULT_CAPTURE
    ref = args.ref or default_ref(context["root"], context["default_branch"])
    report = gaps.find_gaps(context["root"], ref, switch.get("path", "knowledge/"), capture, context["remote"],
                            args.since, switch.get("skip") or [])
    return {**report, "project": context["project"], "text": gaps.format_text(context["project"], report),
            "code": "gaps" if report["gap_count"] else "no_gaps",
            "summary": f"{report['gap_count']} item(s) merged without a note ({report['window']})",
            "next": ("for each gap judge durability: write a note with collect (--issue N, or --base/--head, or --commits) "
                     "or skip it with a one-line reason" if report["gap_count"] else None)}
