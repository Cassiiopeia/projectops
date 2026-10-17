"""레포 탐색 서브커맨드: explore (list-repos|repo-detail|readme|languages|commits)."""
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
                "summary": f"{args.owner} {owner_type} 레포 {len(repos)}개",
                "next": f"explore repo-detail {args.owner} {repos[0]['name']}" if repos else None,
            })
        if not args.repo:
            return emit({"ok": False, "code": "missing_argument", "error": f"explore {args.sub}는 repo 인자 필요"})
        if args.sub == "repo-detail":
            detail = api.get_repo_detail(args.owner, args.repo, pat)
            return emit({
                "repo": detail,
                "summary": f"{args.owner}/{args.repo} 상세",
                "next": f"explore readme {args.owner} {args.repo}",
            })
        if args.sub == "readme":
            readme = api.get_readme(args.owner, args.repo, pat)
            return emit({
                "readme": readme,
                "summary": "README 조회",
                "next": f"explore languages {args.owner} {args.repo}",
            })
        if args.sub == "languages":
            langs = api.get_languages(args.owner, args.repo, pat)
            return emit({"languages": langs, "summary": f"언어 {len(langs)}개"})
        if args.sub == "commits":
            commits = api.list_commits(args.owner, args.repo, pat, limit=args.limit)
            return emit({
                "count": len(commits),
                "commits": commits,
                "summary": f"최근 커밋 {len(commits)}개",
            })
        return emit({"ok": False, "code": "unknown_subcommand", "error": f"알 수 없음: {args.sub}"})
    except GitHubAPIError as e:
        return api_error(e)


# ── 인자 ──

def _configure_explore(parser) -> None:
    parser.add_argument("sub", choices=["list-repos", "repo-detail", "readme", "languages", "commits"])
    parser.add_argument("owner")
    parser.add_argument("repo", nargs="?")
    parser.add_argument("--type", choices=["user", "org", "auto"], default="auto")
    parser.add_argument("--limit", type=int, default=10)


COMMANDS = [
    Command(name="explore", help="레포 탐색 (list-repos|repo-detail|readme|languages|commits)", run=cmd_explore,
            configure=_configure_explore),
]
