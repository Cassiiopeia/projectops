"""Repo admin subcommands: update-repo (visibility only), delete-repo (#1241)
api pass-through keeps blocking admin writes > these two are the only way in (--dry-run, explicit --confirm)"""
from __future__ import annotations

import re

from common.emit import emit
from common.gh_client import GitHubAPIError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat

# Tracked paths that usually hold credentials (checked before going public). Example/sample/template files are skipped
SENSITIVE_PATH_PATTERN = re.compile(
    r"(^|/)(\.env(\.[^/]+)?|id_rsa|id_ed25519|credentials\.json|service[-_]account[^/]*\.json"
    r"|[^/]+\.(pem|key|p12|pfx|jks|keystore|mobileprovision))$",
    re.IGNORECASE)
SAFE_SAMPLE_SUFFIX_PATTERN = re.compile(r"\.(example|sample|template|dist)$", re.IGNORECASE)
# Sensitive paths listed in the response at most
MAX_SENSITIVE_PATHS_SHOWN = 20
PERMISSION_HINT = ("the PAT needs admin rights on the repo: classic PAT scope {scope}, "
                   "or fine-grained PAT permission Administration: write")


def find_sensitive_paths(paths: list[str]) -> list[str]:
    """Tracked file paths > those that look like credentials (samples excluded)"""
    return [path for path in paths
            if SENSITIVE_PATH_PATTERN.search(path) and not SAFE_SAMPLE_SUFFIX_PATTERN.search(path)]


def cmd_update_repo(args, api) -> int:
    """Visibility change: read current > unchanged | dry-run plan | confirm gate > PATCH private"""
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    full_name = f"{args.owner}/{args.repo}"
    confirm_command = f"update-repo {args.owner} {args.repo} --visibility {args.visibility} --confirm"
    try:
        current = _read_repo_or_none(api, args.owner, args.repo, pat)
        if current is None:
            return _emit_repo_not_found(full_name)
        current_visibility = current.get("visibility") or ("private" if current.get("private") else "public")
        if current_visibility == args.visibility:
            return emit({"code": "unchanged", "repo": full_name, "visibility": current_visibility,
                         "summary": f"{full_name} is already {current_visibility}; nothing changed",
                         "next": None})
        warnings = _visibility_warnings(api, args.owner, args.repo, pat, current, args.visibility)
        plan = {"repo": full_name, "current_visibility": current_visibility, "target_visibility": args.visibility,
                "warnings": warnings}
        if args.dry_run:
            return emit({"dry_run": True, **plan,
                         "summary": f"dry run: would change {full_name} from {current_visibility} to {args.visibility}",
                         "next": f"only if the user asked for this change in this conversation: {confirm_command}"})
        if not args.confirm:
            return emit({"ok": False, "code": "confirm_required", **plan,
                         "error": "changing visibility needs --confirm",
                         "summary": f"refused: {full_name} visibility change needs --confirm",
                         "next": f"only if the user asked for this change in this conversation: {confirm_command}"})
        updated = api.update_repo_visibility(args.owner, args.repo, pat, is_private=args.visibility == "private")
        return emit({"repo": updated, "previous_visibility": current_visibility, "warnings": warnings,
                     "summary": f"changed {full_name} from {current_visibility} to {updated.get('visibility') or args.visibility}",
                     "next": f"explore repo-detail {args.owner} {args.repo}"})
    except GitHubAPIError as error:
        return _emit_admin_error(error, full_name, scope="repo")


def cmd_delete_repo(args, api) -> int:
    """Repo deletion: read facts > dry-run facts | confirm gate (full name typed back) > DELETE"""
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    full_name = f"{args.owner}/{args.repo}"
    confirm_command = f"delete-repo {args.owner} {args.repo} --confirm {full_name}"
    try:
        detail = _read_repo_or_none(api, args.owner, args.repo, pat)
        if detail is None:
            return _emit_repo_not_found(full_name)
        facts = _deletion_facts(detail)
        if args.dry_run:
            return emit({"dry_run": True, "repo": full_name, "facts": facts,
                         "warning": "deletion is permanent: code, issues, PRs, releases, wiki and Actions history go away",
                         "summary": f"dry run: would delete {full_name} ({facts['visibility']}, {facts['size_kb']} KB)",
                         "next": f"only if the user asked to delete this repo in this conversation: {confirm_command}"})
        if args.confirm is None:
            return emit({"ok": False, "code": "confirm_required", "repo": full_name, "facts": facts,
                         "error": f"deleting needs --confirm {full_name}",
                         "summary": f"refused: deleting {full_name} needs --confirm {full_name}",
                         "next": f"only if the user asked to delete this repo in this conversation: {confirm_command}"})
        if args.confirm != full_name:
            return emit({"ok": False, "code": "confirm_mismatch", "repo": full_name,
                         "error": f"--confirm must be exactly {full_name}, got {args.confirm}",
                         "summary": f"refused: confirmation does not match {full_name}; nothing deleted",
                         "next": "check the target with the user, then retry with the exact owner/repo"})
        api.delete_repo(args.owner, args.repo, pat)
        return emit({"deleted": full_name, "facts": facts, "summary": f"deleted {full_name}", "next": None})
    except GitHubAPIError as error:
        return _emit_admin_error(error, full_name, scope="delete_repo")


def _read_repo_or_none(api, owner: str, repo: str, pat: str):
    """Repo details | None on 404 (other errors propagate)"""
    try:
        return api.get_repo_detail(owner, repo, pat)
    except GitHubAPIError as error:
        if error.status_code == 404:
            return None
        raise


def _deletion_facts(detail: dict) -> dict:
    """Repo details > the facts shown before deleting"""
    return {"visibility": detail.get("visibility") or ("private" if detail.get("private") else "public"),
            "default_branch": detail.get("default_branch"), "size_kb": detail.get("size_kb", 0),
            "pushed_at": detail.get("pushed_at"), "open_issues": detail.get("open_issues", 0),
            "stars": detail.get("stars", 0), "forks": detail.get("forks", 0),
            "archived": detail.get("archived", False), "fork": detail.get("fork", False), "url": detail.get("url")}


def _visibility_warnings(api, owner: str, repo: str, pat: str, current: dict, target: str) -> list[str]:
    """Cheap pre-change warnings: history, Actions secrets count, tracked credential-like files (going public)"""
    if target == "private":
        return ["forks of a public repo stay public; stars and watchers from people without access are lost"]
    warnings = ["every commit, branch and tag becomes public, including files deleted later but still in history"]
    # Actions secrets (values stay hidden; fork PRs can run workflows) — skipped when the PAT cannot list them
    try:
        secret_names = [secret["name"] for secret in api.list_secrets(owner, repo, pat)]
        if secret_names:
            warnings.append(f"{len(secret_names)} Actions secret(s) ({', '.join(secret_names[:10])}): values stay hidden, "
                            "but anyone can fork and open PRs that run workflows; check pull_request_target workflows")
    except GitHubAPIError:
        warnings.append("could not list Actions secrets with this PAT; check them in the repo settings")
    # Credential-like files on the default branch (one tree call)
    try:
        paths, is_truncated = api.list_tree_paths(owner, repo, current.get("default_branch") or "HEAD", pat)
        sensitive_paths = find_sensitive_paths(paths)
        if sensitive_paths:
            warnings.append(f"{len(sensitive_paths)} tracked file(s) look like credentials: "
                            + ", ".join(sensitive_paths[:MAX_SENSITIVE_PATHS_SHOWN]))
        if is_truncated:
            warnings.append("the file tree is too large to scan fully; credential check is partial")
    except GitHubAPIError:
        warnings.append("could not read the file tree; credential-like files were not checked")
    return warnings


def _emit_repo_not_found(full_name: str) -> int:
    return emit({"ok": False, "code": "repo_not_found",
                 "error": f"{full_name} not found (or the PAT cannot see it)",
                 "summary": f"{full_name} not found; nothing changed",
                 "next": f"check the name with explore list-repos {full_name.split('/')[0]}"})


def _emit_admin_error(error: GitHubAPIError, full_name: str, *, scope: str) -> int:
    """403 > permission hint (scope differs per command), 404 > not found, others > shared api_error"""
    if error.status_code == 403:
        return emit({"ok": False, "code": "github_api_403", "error": str(error),
                     "hint": PERMISSION_HINT.format(scope=scope),
                     "summary": f"GitHub refused the change on {full_name} (403); nothing changed"})
    if error.status_code == 404:
        return _emit_repo_not_found(full_name)
    return api_error(error)


# ── Arguments ──

def _configure_update_repo(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("--visibility", required=True, choices=["public", "private"], help="target visibility")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="show current and target visibility with warnings; change nothing")
    parser.add_argument("--confirm", action="store_true",
                        help="apply the change (pass only after the user asked for it in this conversation)")


def _configure_delete_repo(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="show repo facts (visibility, branch, size, last push, open issues); delete nothing")
    parser.add_argument("--confirm", default=None, metavar="OWNER/REPO",
                        help="the exact owner/repo typed back; deletes permanently (only after the user asked)")


COMMANDS = [
    Command(name="update-repo", help="change repo visibility only (public|private); needs --confirm",
            run=cmd_update_repo, configure=_configure_update_repo),
    Command(name="delete-repo", help="delete a repo permanently; needs --confirm OWNER/REPO",
            run=cmd_delete_repo, configure=_configure_delete_repo),
]
