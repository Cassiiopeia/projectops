"""brain_cli subcommands: parse input > call module > result + next (status, collect, setup, gaps)
Read-only except setup --apply --yes, which the agent runs only after the user agreed.
"""
from __future__ import annotations

import difflib
from pathlib import Path

from . import collect, contracts, gaps, notes, onboarding, registry, repo_facts, switch_edit

DEFAULT_CAPTURE = "issue-end"   # repos switched on before capture modes existed keep the issue flow


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
            # Repo switch first (shared with teammates), then the owner's registry
            "brain_mcp": switch.get("brain_mcp") or (sync_target.get("mcp_server_name") if sync_target.get("known") else None),
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
    open_questions = [name for name, is_open in (("capture", not switch.get("capture")),
                                                 ("rule_block", state == "absent")) if is_open]
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


def _setup_questions(context: dict, recommendation: dict, onboarding_state: dict, options: list[dict]) -> list[dict]:
    """At most two questions, each with a recommended answer so 'yes' is enough"""
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
    return questions


def cmd_setup(args) -> dict:
    context = repo_context(args.repo)
    root, switch = context["root"], context["switch"]
    recommendation = onboarding.recommend_capture(root, default_ref(root, context["default_branch"]), context["remote"])
    capture = args.capture or switch.get("capture") or recommendation["mode"]
    brain_mcp = args.brain_mcp or context["brain_mcp"]
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
    if args.brain_mcp:
        updates["brain_mcp"] = args.brain_mcp
    detected_rules = onboarding.detect_rules_file(root) if not switch.get("rules") else None
    if detected_rules:
        updates["rules"] = detected_rules   # the repo's own vault rules win over the default note format
    # Turning on is part of onboarding when the switch is off: the plan previews it, apply needs --enable
    needs_enable = not switch["enabled"]
    if args.enable or (needs_enable and not args.apply):
        updates["enabled"] = True
    try:
        new_version_text = (switch_edit.set_knowledge_keys(context["text"], updates, create_if_missing="enabled" in updates)
                            if updates else context["text"])
        switch_error = None
    except switch_edit.SwitchEditError as error:
        new_version_text, switch_error = context["text"], str(error)
    plan = {"recommended_capture": recommendation, "capture": capture, "brain_mcp": brain_mcp, "files": files,
            "target_options": options, "target": target, "target_kind": target_kind, "block": block,
            "block_state": onboarding_state["rule_block_state"],
            "questions": _setup_questions(context, recommendation, onboarding_state, options),
            "switch_updates": updates, "switch_error": switch_error,
            "version_yml_diff": "".join(difflib.unified_diff(
                context["text"].splitlines(keepends=True), new_version_text.splitlines(keepends=True),
                fromfile="a/version.yml", tofile="b/version.yml", n=1)),
            "block_diff": onboarding.preview_diff(root / target, target, block)}
    if not args.apply:
        return {**plan, "code": "plan", "summary": f"{len(plan['questions'])} question(s); recommended capture {recommendation['mode']}, "
                f"rule block target {target} ({target_kind})",
                "next": "ask the questions (recommended answer first, in the user's language), then "
                        f"setup --apply --yes{' --enable' if needs_enable else ''} --capture MODE --claude-md add|decline [--target PATH]"}
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
    if args.claude_md == "add" or (args.claude_md is None and onboarding_state["rule_block_state"] == "outdated"):
        outcome = onboarding.apply_block(root / target, block)
        written.append(f"{target} ({outcome})")
        if args.agents_md and files["agents_md_needs_block"]:
            written.append(f"AGENTS.md ({onboarding.apply_block(root / 'AGENTS.md', block)})")
    follow_up = ["commit the tracked files above with pro-commit (stage only these paths)"]
    if target_kind == "local-claude-md+worktree-copy" and args.claude_md == "add":
        follow_up.insert(0, f"python3 ~/.projectops/bin/projectops_cli.py init-worktree record --root {root} --copied {target}")
    return {**plan, "code": "applied", "written": written, "summary": f"wrote {', '.join(written) or 'nothing'}",
            "next": "; then ".join(follow_up)}


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
