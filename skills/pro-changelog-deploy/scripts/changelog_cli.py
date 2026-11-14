#!/usr/bin/env python3
"""changelog_cli — CLI for the changelog-deploy skill.

deploy PR automation + combined Actions/CodeRabbit status.
Subcommands: actions, deploy-status, list-prs, update-pr, create-pr, sync-base, detect-release-context

Usage:
    cd skills/pro-changelog-deploy/scripts
    python changelog_cli.py <subcommand> [args]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402
from common.emit import emit  # noqa: E402
from common.config import get_github_pat  # noqa: E402
from common.gh_client import (  # noqa: E402
    GitHubAPIError,
    list_pulls, update_pull_request,
    get_run, get_job_log, list_failed_runs, resolve_pr_runs, resolve_branch_runs,
)

# Find sibling modules even when loaded by file path (tests, harness)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_status import cmd_deploy_status  # noqa: E402,F401
from release_tools import branches_check, cmd_sync_base, detect_release_shape, wrap_release_notes  # noqa: E402,F401
from release_context import collect_app_signals, load_config as _load_config  # noqa: E402
from release_language import collect_release_language  # noqa: E402
from release_pr import cmd_create_pr, _resolve_body_file  # noqa: E402,F401


def cmd_actions(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "no PAT configured"})
    try:
        if args.sub == "show-run":
            if args.arg is None:
                return emit({"ok": False, "code": "missing_argument", "error": "RUN_ID is required"})
            data = get_run(args.owner, args.repo, int(args.arg), pat)
            if data.get("failed_job_ids"):
                data["next"] = f"actions joblog {args.owner} {args.repo} {data['failed_job_ids'][0]}"
            return emit(data)
        if args.sub == "joblog":
            if args.arg is None:
                return emit({"ok": False, "code": "missing_argument", "error": "JOB_ID is required"})
            data = get_job_log(args.owner, args.repo, int(args.arg), pat, grep=args.grep, tail=args.tail)
            return emit(data)
        if args.sub == "list-failed":
            runs = list_failed_runs(args.owner, args.repo, pat, limit=args.limit)
            nxt = f"actions show-run {args.owner} {args.repo} {runs[0]['run_id']}" if runs else None
            return emit({"count": len(runs), "runs": runs, "next": nxt})
        if args.sub == "resolve-pr":
            if args.arg is None:
                return emit({"ok": False, "code": "missing_argument", "error": "PR_NUM is required"})
            data = resolve_pr_runs(args.owner, args.repo, int(args.arg), pat)
            failed = [r for r in data["runs"] if r["conclusion"] == "failure"]
            data["next"] = f"actions show-run {args.owner} {args.repo} {failed[0]['run_id']}" if failed else None
            return emit(data)
        if args.sub == "resolve-branch":
            if args.arg is None:
                return emit({"ok": False, "code": "missing_argument", "error": "BRANCH is required"})
            runs = resolve_branch_runs(args.owner, args.repo, args.arg, pat, limit=args.limit)
            failed = [r for r in runs if r["conclusion"] == "failure"]
            nxt = f"actions show-run {args.owner} {args.repo} {failed[0]['run_id']}" if failed else None
            return emit({"branch": args.arg, "count": len(runs), "runs": runs, "next": nxt})
        return emit({"ok": False, "code": "unknown_subcommand", "error": f"unknown: {args.sub}"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})
    except ValueError as e:
        return emit({"ok": False, "code": "invalid_argument", "error": str(e)})


def cmd_list_prs(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "no PAT configured"})
    try:
        result = list_pulls(args.owner, args.repo, pat, args.state)
        return emit({
            "count": len(result),
            "prs": result,
            "summary": f"{args.owner}/{args.repo}: {len(result)} PR(s) ({args.state})",
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_update_pr(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "no PAT configured"})
    body = None
    if args.body_file:
        body_path = _resolve_body_file(args.body_file)
        body = body_path.read_text(encoding="utf-8") if body_path else None
    # Nothing to change: skip the PATCH and say so — never misreport "updated" (#699)
    if args.title is None and body is None and args.state is None:
        return emit({
            "ok": False,
            "code": "nothing_to_update",
            "error": "nothing to change (need one of --title/--body-file/--state)",
        })
    try:
        result = update_pull_request(
            args.owner, args.repo, args.number, pat,
            title=args.title, body=body, state=args.state,
        )
        return emit({**result, "summary": f"updated PR #{args.number}"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def _normalize_provider(provider: str, project_root: Path) -> str:
    """Normalize unset/retired provider values with the same rules as the workflow (#821).

    The unset rule must match the workflow (RELEASE-CHANGELOG) 3-step rule:
    explicit value → (if .coderabbit.yaml exists) coderabbit → commit. If they differ, skill and workflow decide differently."""
    if not provider:
        provider = "coderabbit" if (project_root / ".coderabbit.yaml").is_file() else "commit"
    if provider == "github-ai":
        # Service retired (2026-07-30) — absorbed into commit, same as ladder.py (#821).
        # Passing it through would make the skill present a retired generator as a valid provider.
        provider = "commit"
    return provider


def _parse_release_branches(project_root: Path) -> tuple[dict, dict]:
    """Read version.yml and return (value, explicit).

    explicit means the key was actually written in version.yml — so when a fallback and the config value
    disagree, the agent can tell whether "version.yml really says so" (#842)."""
    vy = project_root / "version.yml"
    text = ""
    if vy.exists():
        try:
            text = vy.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""

    def _find(pattern):
        m = re.search(pattern, text, re.MULTILINE)
        return m.group(1) if m else None

    # Development branch key: development_branch (canonical) > deploy_branch (old name) (#915)
    head = (_find(r"^\s*development_branch\s*:\s*[\"']?([A-Za-z0-9._/-]+)")
            or _find(r"^\s*deploy_branch\s*:\s*[\"']?([A-Za-z0-9._/-]+)"))
    base = _find(r"^\s*default_branch\s*:\s*[\"']?([A-Za-z0-9._/-]+)")
    provider = _find(r"^\s*provider\s*:\s*[\"']?([a-z-]+)")
    values = {
        "head": head or "develop",
        "base": base or "main",
        "provider": _normalize_provider(provider or "", project_root),
    }
    explicit = {"head": head is not None, "base": base is not None, "provider": provider is not None}
    return values, explicit


def _read_release_branches(project_root: Path) -> dict:
    """Read release branches and changelog provider from version.yml (#456, SSOT).

    - head = metadata.development_branch (release PR head) > old key deploy_branch > 'develop' fallback.
    - base = metadata.default_branch (repo default) — 'main' fallback if missing.
    - provider = metadata.template.options.changelog.provider — if missing, 'coderabbit' when
      .coderabbit.yaml exists in the repo root, otherwise 'commit' (#821, same as the workflow).
      A stored retired 'github-ai' value is returned as 'commit'.
    Parsed with regexes only, no yaml dependency (offline networks, standard library first)."""
    return _parse_release_branches(project_root)[0]


# branches key ↔ config changelog_deploy key. config uses human-readable names (head_branch).
_BRANCH_CONFIG_KEYS = (("head", "head_branch"), ("base", "base_branch"), ("provider", "provider"))


def _detect_owner_repo(project_root: Path) -> tuple[str | None, str | None]:
    """Extract owner/repo from the origin URL. On failure (None, None) — only the config comparison is skipped."""
    import subprocess
    try:
        url = subprocess.run(
            ["git", "-C", str(project_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, None
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    return (m.group(1), m.group(2)) if m else (None, None)


def _release_config_view(config: dict | None, owner: str | None, repo: str | None) -> dict:
    """Extract this repo's branch/provider record from config, plus global keys no longer read (#842).

    Global `github.changelog_deploy.{head_branch,base_branch,provider}` put repo knowledge machine-wide
    and overrode other repos' version.yml. Its values are not used; only the fact that it remains is reported."""
    gh = (config or {}).get("github") if isinstance(config, dict) else None
    gh = gh if isinstance(gh, dict) else {}
    glob = gh.get("changelog_deploy") if isinstance(gh.get("changelog_deploy"), dict) else {}
    ignored_global = sorted(k for _, k in _BRANCH_CONFIG_KEYS if k in glob)

    repo_values: dict = {}
    repo_entry = False
    if owner and repo:
        for r in gh.get("repos", []) or []:
            if isinstance(r, dict) and r.get("owner") == owner and r.get("repo") == repo:
                repo_entry = True
                cd = r.get("changelog_deploy") if isinstance(r.get("changelog_deploy"), dict) else {}
                repo_values = {k: cd[k] for _, k in _BRANCH_CONFIG_KEYS if cd.get(k)}
                break
    return {
        "found": config is not None,
        "repo_entry": repo_entry,
        "repo_values": repo_values,
        "ignored_global_keys": ignored_global,
    }


def cmd_detect_release_context(args) -> int:
    """Collect 'signals' of whether this repo leads straight to app store review, returned as JSON.

    The decision (confirming an app review repo, asking the user, updating config) is the agent's. py gives only facts (signals)
    and a weak hint. No GitHub API, so no PAT needed (scans local files only)."""
    project_root = Path(args.project_root).resolve() if args.project_root else Path.cwd()
    if not project_root.is_dir():
        # Treating a missing path as empty signals would misjudge it as "not an app review repo" (#713)
        return emit({"ok": False, "code": "not_found",
                     "summary": "the --project-root path does not exist",
                     "error": f"the --project-root path does not exist: {project_root}"})

    signals, hint = collect_app_signals(project_root)

    next_hint = (
        "agent: if app_release is not recorded, confirm once with the user and save it to config"
        if hint in ("strong_app", "app_release_likely", "unknown")
        else "agent: backend_only; pass quietly, no warnings or questions"
    )

    # Release branches · provider (#456) — the skill uses these instead of hardcoded develop/main.
    # The canonical source is version.yml (#842). Reading the same place as the workflow keeps skill and workflow in agreement.
    branches, explicit = _parse_release_branches(project_root)
    has_version_yml = (project_root / "version.yml").is_file()

    owner, repo = args.owner, args.repo
    if not (owner and repo):
        owner, repo = _detect_owner_repo(project_root)
    view = _release_config_view(_load_config(args.config), owner, repo)
    repo_values = view["repo_values"]

    conflict = []
    if has_version_yml:
        # version.yml wins. Per-repo config values may be a stale cache, so a mismatch is only reported.
        source = "version.yml"
        for key, cfg_key in _BRANCH_CONFIG_KEYS:
            if cfg_key in repo_values and repo_values[cfg_key] != branches[key]:
                conflict.append({
                    "key": cfg_key,
                    "version_yml": branches[key],
                    "config": repo_values[cfg_key],
                    "version_yml_explicit": explicit[key],
                })
    elif repo_values:
        # Only repos without version.yml use the per-repo config record. Missing keys use the fallback rules.
        source = "config"
        for key, cfg_key in _BRANCH_CONFIG_KEYS:
            if cfg_key in repo_values:
                value = repo_values[cfg_key]
                branches[key] = _normalize_provider(value, project_root) if key == "provider" else value
    else:
        source = "fallback"

    if conflict:
        next_hint = ("agent: go ahead with the version.yml values and tell the user about the difference in one line. "
                     "That key in the per-repo config is a stale record. " + next_hint)
    elif source == "fallback" and not has_version_yml:
        next_hint = ("agent: no version.yml; settle the branches (ask if unclear) and record them in the per-repo config. "
                     + next_hint)

    check = branches_check(project_root, branches["head"], branches["base"])
    # Repos that release main > deploy without a development branch (#970)
    shape = detect_release_shape(project_root, branches, check)
    if shape["release_shape"] == "deploy_branch":
        next_hint = ("agent: deploy-branch repo; follow release_steps with the head/base of release_branches "
                     "instead of branches. Confirm the pair once with the user. " + next_hint)
    elif shape["release_shape"] == "three_tier":
        next_hint = ("agent: development > default > deploy repo; the release PR uses branches as usual, then "
                     "promote_branches carries it to the deploy branch. Follow release_steps. " + next_hint)

    return emit({
        "ok": True,
        # Always a string (#970)
        "summary": (f"release {branches['head']} > {branches['base']} ({source}), app review hint={hint}"
                    if shape["release_shape"] == "standard" else
                    f"three-tier repo: release {branches['head']} > {branches['base']}, deploy "
                    f"{shape['promote_branches']['head']} > {shape['promote_branches']['base']}, app review hint={hint}"
                    if shape["release_shape"] == "three_tier" else
                    f"deploy-branch repo: {shape['release_branches']['head']} > "
                    f"{shape['release_branches']['base']}, app review hint={hint}"),
        "project_root": str(project_root),
        "signals": signals,
        "branches": branches,   # {head, base, provider} — release PR from head→base
        # version.yml (canonical) | config (per-repo record for repos without version.yml) | fallback (nothing found)
        "branches_source": source,
        "conflict": conflict,   # filled only when version.yml ≠ per-repo config
        "config": {
            "owner": owner,
            "repo": repo,
            "repo_entry": view["repo_entry"],
            # Global keys no longer read — if present, the user should clean them up
            "ignored_global_keys": view["ignored_global_keys"],
        },
        "hint": hint,
        # Note language · title · store languages · fixed store text (#977) — read before writing notes
        "release_language": collect_release_language(project_root),
        "branches_check": check,
        **shape,
        "next": next_hint,
    })


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="changelog_cli", description="changelog-deploy skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_a = sub.add_parser("actions", help="look up GitHub Actions runs, jobs and logs")
    p_a.add_argument("sub", choices=["show-run", "joblog", "list-failed", "resolve-pr", "resolve-branch"])
    p_a.add_argument("owner")
    p_a.add_argument("repo")
    p_a.add_argument("arg", nargs="?")
    p_a.add_argument("--limit", type=int, default=10)
    p_a.add_argument("--grep", default="error")
    p_a.add_argument("--tail", type=int, default=30)
    p_a.set_defaults(func=cmd_actions)

    p_ds = sub.add_parser("deploy-status", help="overall verdict on the deploy PR state")
    p_ds.add_argument("owner")
    p_ds.add_argument("repo")
    p_ds.add_argument("--pr", type=int)
    p_ds.add_argument("--base", default="main")
    p_ds.add_argument("--wait", type=int, default=0, metavar="SECONDS",
                      help="while automerge is pending, poll inside the tool for up to this many seconds (max 540). Use instead of sleep")
    p_ds.add_argument("--head", default=None, help="head branch of the release PR (without it, only dependency bot PRs are excluded)")
    p_ds.set_defaults(func=cmd_deploy_status)

    p_lp = sub.add_parser("list-prs", help="list PRs")
    p_lp.add_argument("owner")
    p_lp.add_argument("repo")
    p_lp.add_argument("--state", choices=["open", "closed", "all"], default="open")
    p_lp.set_defaults(func=cmd_list_prs)

    p_up = sub.add_parser("update-pr", help="update a PR body or state")
    p_up.add_argument("owner")
    p_up.add_argument("repo")
    p_up.add_argument("number", type=int)
    p_up.add_argument("body_file", nargs="?")
    p_up.add_argument("--title")
    p_up.add_argument("--state", choices=["open", "closed"])
    p_up.set_defaults(func=cmd_update_pr)

    p_cp = sub.add_parser("create-pr", help="create the deploy PR (also used to re-trigger)")
    p_cp.add_argument("owner")
    p_cp.add_argument("repo")
    p_cp.add_argument("title")
    p_cp.add_argument("body_file")
    p_cp.add_argument("head")
    p_cp.add_argument("base")
    p_cp.add_argument("--allow-empty", action="store_true",
                      help="create the PR even if head has no commits ahead of base (default: refuse with nothing_to_deploy)")
    # App review approval gate (#970): where app signals were judged and the user's approval marker
    p_cp.add_argument("--project-root", help="repo root to check for app review signals (default: cwd)")
    p_cp.add_argument("--user-approved", action="store_true",
                      help="add only when the user reviewed and approved the release notes in an app review repo (otherwise needs_user_approval)")
    p_cp.set_defaults(func=cmd_create_pr)

    p_sb = sub.add_parser("sync-base", help="merge base into head before deploying (fetch > check the difference > merge; stops on conflict)")
    p_sb.add_argument("--head", required=True, help="release head branch (must be checked out)")
    p_sb.add_argument("--base", required=True, help="release base branch")
    p_sb.add_argument("--project-root", help="repo root (default: cwd)")
    p_sb.set_defaults(func=cmd_sync_base)

    # Collect 'signals' of app store review relevance (judgement and confirmation by the agent). No PAT — scans local files only.
    p_drc = sub.add_parser("detect-release-context", help="collect signals that the repo feeds app store review (signals/hint JSON)")
    p_drc.add_argument("--project-root", help="absolute repo root path (default: cwd)")
    # For config comparison (#842) — when omitted, uses the origin URL and fixed config path. config is read only.
    p_drc.add_argument("--owner", help="repo owner (default: taken from the origin URL)")
    p_drc.add_argument("--repo", help="repo name (default: taken from the origin URL)")
    p_drc.add_argument("--config", help="config.json path (default: ~/.projectops/config/config.json)")
    p_drc.set_defaults(func=cmd_detect_release_context)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
