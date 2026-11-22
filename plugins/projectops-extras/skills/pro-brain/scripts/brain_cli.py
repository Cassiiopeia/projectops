#!/usr/bin/env python3
"""brain_cli: pro-brain fact collection — the agent decides and writes the note, output is always JSON (ok, code, summary, next)
Read-only: never writes files, never talks to any brain. extras installs only its own folder, so standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brain import collect, registry, repo_facts  # noqa: E402


class _BadArgumentsExit(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class JsonArgumentParser(argparse.ArgumentParser):
    """Parser that returns argument errors as JSON instead of stderr"""

    def error(self, message):
        raise _BadArgumentsExit(message)


def emit(payload: dict) -> int:
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()
    return 0 if payload["ok"] else 1


def _repo_context(repo_argument: str | None) -> dict:
    """Repo root, remote, branch, version.yml facts, repo switch and private registry match"""
    root = repo_facts.find_repo_root(Path(repo_argument or ".").resolve())
    if root is None:
        raise LookupError("not inside a git repository")
    remote = repo_facts.read_remote_slug(root)
    section = registry.load_section()
    project_key, entry = registry.find_project(section, remote, root) if section else (None, None)
    return {"root": root, "remote": remote, "section": section, "project_key": project_key, "entry": entry or {}}


# Subcommands: parse input > call module > result + next

def cmd_status(args) -> dict:
    context = _repo_context(args.repo)
    text = repo_facts.read_version_yml_text(context["root"])
    switch = repo_facts.read_knowledge_switch(text)
    sync_target = registry.describe_sync_target(context["section"], context["project_key"], context["entry"])
    result = {"repo_root": str(context["root"]), "remote": context["remote"], "project_key": context["project_key"],
              "switch": switch, "sync_target": sync_target}
    if not switch["enabled"]:
        intent = sync_target.get("registry_intent", {}) if sync_target.get("known") else {}
        hint = (" The private registry wants it on: propose the version.yml block to the user (do not write it unasked)."
                if intent.get("enabled") else "")
        return {**result, "code": "switch_off",
                "summary": "knowledge capture is off for this repo (version.yml metadata.template.options.knowledge.enabled is not true)." + hint,
                "next": "stop: tell the user in one line that pro-brain is off for this repo"}
    folder = context["root"] / switch["path"]
    result["knowledge_folder_exists"] = folder.is_dir()
    # rules is relative to the repo root; template is relative to the knowledge folder
    if "rules" in switch:
        result["rules_exists"] = (context["root"] / str(switch["rules"])).is_file()
    if "template" in switch:
        result["template_exists"] = (folder / str(switch["template"])).is_file()
    sync_line = (f"synced by brain '{sync_target['brain']}' as source '{sync_target['source_id']}'" if sync_target["known"]
                 else f"no sync target known on this machine ({sync_target['reason']}); the note is still written")
    return {**result, "code": "switch_on",
            "summary": f"knowledge capture is on: notes go to {switch['path']}; {sync_line}",
            "next": "judge whether this issue produced durable knowledge; if yes run collect, if not skip with a one-line reason"}


def cmd_collect(args) -> dict:
    context = _repo_context(args.repo)
    root = context["root"]
    branch = args.branch or repo_facts.current_branch(root)
    issue = args.issue or collect.issue_from_branch(branch)
    working_facts = repo_facts.read_version_facts(repo_facts.read_version_yml_text(root))
    switch = repo_facts.read_knowledge_switch(repo_facts.read_version_yml_text(root))
    commit_range = collect.resolve_range(root, args.base, args.head, issue, branch,
                                         working_facts["development_branch"], working_facts["default_branch"])
    # Version and build number as of the issue's last commit, not today's working tree
    head_facts = repo_facts.read_version_facts(repo_facts.read_version_yml_text(root, commit_range["head"]))
    # The checked-out branch is the issue branch only in branch mode; otherwise record it only when passed
    if commit_range["mode"] != "branch" and not args.branch:
        branch = None
    registry_repo = registry.matching_repo(context["entry"], context["remote"]) if context["entry"] else {}
    files = collect.changed_files(root, commit_range, switch.get("path", "knowledge/"))
    changes = collect.summarize_changes(files, collect.stack_paths(registry_repo, head_facts))
    captured = collect.now_seoul()
    metadata = {
        # Registry key when known, else the repo name, so teammates without the registry still get a stable key
        "project": context["project_key"] or (context["remote"] or root.name).split("/")[-1].lower(),
        "stacks": changes["stacks"],
        "app_version": head_facts["version"],
        "build_number": head_facts["version_code"],
        "issue": issue,
        "issue_url": f"https://github.com/{context['remote']}/issues/{issue}" if issue and context["remote"] else None,
        "pr": args.pr_number,
        "pr_url": args.pr_url,
        "branch": branch,
        "commit_base": commit_range["base"],
        "commit_head": commit_range["head"],
        "commit_count": len(commit_range["commits"]),
        "deploy_target": args.deploy_target,
        "deploy_version": args.deploy_version,
        "changed_modules": changes["changed_modules"],
        "main_files": changes["main_files"],
        "captured_at": captured.isoformat(timespec="seconds"),
        "captured_by": "pro-brain",
    }
    missing = [name for name, value in (("pr", args.pr_number), ("branch", branch), ("deploy_target", args.deploy_target))
               if not value]
    return {
        "range_mode": commit_range["mode"],
        "created": captured.date().isoformat(),
        "changed_file_count": changes["changed_file_count"],
        "metadata": metadata,
        "frontmatter": "\n".join(collect.frontmatter_lines(metadata)),
        "switch": switch,
        "summary": f"{len(commit_range['commits'])} commit(s), {changes['changed_file_count']} file(s), "
                   f"stacks {', '.join(changes['stacks']) or 'none'}",
        "next": ("write the note: repo rules/template first, pro-brain keys appended to its frontmatter"
                 + (f"; not given: {', '.join(missing)} (pass --pr-number/--pr-url/--branch from pro-github list-prs, "
                    "--deploy-target/--deploy-version when a deploy ran)" if missing else "")),
    }


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="brain_cli.py", description="pro-brain fact collection (read-only)")
    sub = parser.add_subparsers(dest="command", parser_class=JsonArgumentParser)
    status = sub.add_parser("status", help="repo switch + sync target known on this machine")
    status.add_argument("--repo", help="repository folder (default: current folder)")
    gather = sub.add_parser("collect", help="metadata for one issue's note")
    gather.add_argument("--repo", help="repository folder (default: current folder)")
    gather.add_argument("--issue", type=int, help="issue number (default: from the branch name)")
    gather.add_argument("--base", help="commit before the issue's first commit (explicit range)")
    gather.add_argument("--head", help="last commit of the issue (default: HEAD)")
    gather.add_argument("--branch", help="branch name to record (default: current branch)")
    gather.add_argument("--pr-number", type=int)
    gather.add_argument("--pr-url")
    gather.add_argument("--deploy-target", help="where it was deployed, e.g. server, play, testflight")
    gather.add_argument("--deploy-version", help="released version, e.g. 1.2.3")
    return parser


COMMANDS = {"status": cmd_status, "collect": cmd_collect}


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except _BadArgumentsExit as error:
        return emit({"ok": False, "code": "bad_args", "summary": error.message, "next": "brain_cli.py status | collect --help"})
    if not args.command:
        return emit({"ok": False, "code": "bad_args", "summary": "usage: brain_cli.py status | collect [options]",
                     "next": "brain_cli.py status"})
    try:
        return emit(COMMANDS[args.command](args))
    except LookupError as error:
        return emit({"ok": False, "code": "not_a_repo", "summary": str(error), "next": "run inside the project repository or pass --repo"})
    except collect.RangeError as error:
        return emit({"ok": False, "code": "range_unknown", "summary": str(error),
                     "next": "collect --base <sha> [--head <sha>]  or  collect --issue <N>"})
    except repo_facts.GitError as error:
        return emit({"ok": False, "code": "git_error", "summary": str(error), "next": "check the refs you passed"})


if __name__ == "__main__":
    sys.exit(main())
