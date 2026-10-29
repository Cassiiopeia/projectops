"""레포 서브커맨드: explore (list-repos|repo-detail|readme|languages|commits), create-repo."""
from __future__ import annotations

from common.emit import emit
from common.gh_client import GitHubAPIError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat


def cmd_explore(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        if args.sub == "list-repos":
            owner_type = api.get_user_type(args.owner, pat) if args.type == "auto" else args.type
            repos = api.list_repos(args.owner, owner_type, pat)
            return emit({
                "owner": args.owner,
                "owner_type": owner_type,
                "count": len(repos),
                "repos": repos,
                "summary": f"{args.owner} ({owner_type}): {len(repos)} repo(s)",
                "next": f"explore repo-detail {args.owner} {repos[0]['name']}" if repos else None,
            })
        if not args.repo:
            return emit({"ok": False, "code": "missing_argument", "error": f"explore {args.sub} needs a repo argument"})
        if args.sub == "repo-detail":
            detail = api.get_repo_detail(args.owner, args.repo, pat)
            return emit({
                "repo": detail,
                "summary": f"{args.owner}/{args.repo} details",
                "next": f"explore readme {args.owner} {args.repo}",
            })
        if args.sub == "readme":
            readme = api.get_readme(args.owner, args.repo, pat)
            return emit({
                "readme": readme,
                "summary": "fetched README",
                "next": f"explore languages {args.owner} {args.repo}",
            })
        if args.sub == "languages":
            langs = api.get_languages(args.owner, args.repo, pat)
            return emit({"languages": langs, "summary": f"{len(langs)} language(s)"})
        if args.sub == "commits":
            commits = api.list_commits(args.owner, args.repo, pat, limit=args.limit)
            return emit({
                "count": len(commits),
                "commits": commits,
                "summary": f"{len(commits)} recent commit(s)",
            })
        return emit({"ok": False, "code": "unknown_subcommand", "error": f"unknown: {args.sub}"})
    except GitHubAPIError as e:
        return api_error(e)


def cmd_create_repo(args, api) -> int:
    """새 레포 1개: 이미 있으면 repo_exists > dry-run 이면 계획만 > 생성 (#1007)"""
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    full_name = f"{args.owner}/{args.repo}"
    try:
        # 중복 확인 (404 만 "없음")
        try:
            existing = api.get_repo_detail(args.owner, args.repo, pat)
            return emit({"ok": False, "code": "repo_exists", "repo": existing,
                         "error": f"{full_name} already exists",
                         "summary": f"{full_name} already exists; nothing created",
                         "next": f"explore repo-detail {args.owner} {args.repo}"})
        except GitHubAPIError as e:
            if e.status_code != 404:
                raise
        visibility = "private" if args.private else "public"
        if args.dry_run:
            return emit({"dry_run": True, "would_create": full_name, "visibility": visibility,
                         "auto_init": args.auto_init,
                         "summary": f"dry run: would create {visibility} repo {full_name}",
                         "next": f"create-repo {args.owner} {args.repo}" + (" --private" if args.private else "")})
        created = api.create_repo(args.owner, args.repo, pat, is_private=args.private,
                                  description=args.description, should_auto_init=args.auto_init)
        return emit({"repo": created, "summary": f"created {visibility} repo {created.get('full_name') or full_name}",
                     "next": f"explore repo-detail {args.owner} {args.repo}"})
    except GitHubAPIError as e:
        return api_error(e)


# ── 인자 ──

def _configure_explore(parser) -> None:
    parser.add_argument("sub", choices=["list-repos", "repo-detail", "readme", "languages", "commits"])
    parser.add_argument("owner")
    parser.add_argument("repo", nargs="?")
    parser.add_argument("--type", choices=["user", "org", "auto"], default="auto")
    parser.add_argument("--limit", type=int, default=10)


def _configure_create_repo(parser) -> None:
    parser.add_argument("owner", help="user (must be the PAT owner) or organization")
    parser.add_argument("repo", help="new repository name")
    parser.add_argument("--private", action="store_true", help="create as private (default public)")
    parser.add_argument("--description", default=None)
    parser.add_argument("--auto-init", dest="auto_init", action="store_true", help="create with an initial README commit")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="check and show the plan without creating")


COMMANDS = [
    Command(name="explore", help="explore repos (list-repos|repo-detail|readme|languages|commits)", run=cmd_explore,
            configure=_configure_explore),
    Command(name="create-repo", help="create a repository for the PAT user or an organization", run=cmd_create_repo,
            configure=_configure_create_repo),
]
