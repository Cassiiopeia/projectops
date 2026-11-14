#!/usr/bin/env python3
"""commit_cli — CLI for the commit skill.

Branch name → issue number, issue title lookup, commit template generation.
Subcommands: get-issue-number, get-issue, normalize-title, get-commit-template,
resolve-style, sanitize-message, commit

Usage:
    cd skills/pro-commit/scripts
    python commit_cli.py <subcommand> [args]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402
from common.config import get_github_pat  # noqa: E402
from common.gh_client import GitHubAPIError, get_issue  # noqa: E402
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402


def cmd_get_issue_number(_args) -> int:
    from common.issue_number import (
        extract_from_path as in_extract_from_path,
        extract_from_branch, get_current_branch, resolve,
    )
    cwd = os.getcwd()
    wt_number = in_extract_from_path(cwd)
    branch = get_current_branch()
    br_number = extract_from_branch(branch) if branch else None
    number, mismatch = resolve(wt_number, br_number)
    return emit({
        "number": number,
        "mismatch": mismatch,
        "summary": str(number) if number else "no issue number",
    })


def cmd_get_issue(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "no PAT configured"})
    try:
        issue = get_issue(args.owner, args.repo, args.number, pat)
        return emit({
            "issue": issue,
            "title": issue["title"],
            "url": issue["url"],
            "html_url": issue["url"],  # alias for agents guessing the original GitHub key name
            "summary": f"#{issue['number']} — {issue['title']}",
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_normalize_title(args) -> int:
    from common.title import normalize
    result = normalize(" ".join(args.title))
    return emit({"normalized": result, "summary": result})


def _commit_type_arg(value: str) -> str:
    from common.gh_branch import commit_type_arg
    return commit_type_arg(value)


def _non_empty_path_arg(value: str) -> str:
    """Path argument: reject empty or whitespace-only values (an empty $VAR used to commit to the current folder's repo, #1187)"""
    if not value.strip():
        import argparse
        raise argparse.ArgumentTypeError(
            "the path is empty (an unset shell variable?); pass the real path or drop the option")
    return value


def _style(args) -> tuple:
    """Decide the commit format from personal preferences + team version.yml."""
    from common.commit_style import resolve_for_repo
    return resolve_for_repo(getattr(args, "repo_root", None))


def cmd_resolve_style(args) -> int:
    from common.commit_style import _toplevel
    from common.repo_language import read_team_language
    prefs, style = _style(args)
    v = prefs["values"]
    # Language: personal setting > team version.yml language (#977) > none (default behaviour)
    team_language = read_team_language(getattr(args, "repo_root", None) or _toplevel())
    language = v.get("language") or team_language
    language_source = "preferences" if v.get("language") else ("version.yml" if team_language else None)
    return emit({**style, "language": language, "language_source": language_source, "tone": v.get("tone"),
                 "rules": v.get("rules", []), "examples": v.get("examples", []),
                 "ignored": prefs["ignored"], "summary": f"{style['preset']} ({style['source']})"})


def cmd_get_commit_template(args) -> int:
    from common.commit_style import render_for_issue
    _, style = _style(args)
    # When the type is omitted, apply the team commit_type_map too — so the type matches the issue helper comment
    template = render_for_issue(style, issue_title=args.issue_title, issue_url=args.issue_url,
                                commit_type=getattr(args, "commit_type", None),
                                scope=getattr(args, "scope", None) or "")
    return emit({"template": template, "source": style["source"], "warnings": style["warnings"],
                 "summary": template})


def cmd_sanitize_message(args) -> int:
    """Remove @mention trailers at the end of a commit message (last line of defence against AI traces).

    Why Python — this used to be a one-line shell sed, but the `:a;$!N;$!ba` label syntax
    is GNU sed only, so on macOS (BSD sed) it **passed silently with exit code 0**
    and let the input through unchanged. The safety net was believed on while it was actually off.
    Done in Python to avoid per-OS tool differences (#523).

    Only mentions **attached at the end** are removed, not anywhere in the body —
    a mention used meaningfully in the body like "@projectops build app related fix" must be kept.
    """
    cleaned, removed = _strip_trailing_mentions(args.message)
    if getattr(args, "raw", False):
        # Only the cleaned message as is, so the shell need not unpack JSON (#940)
        sys.stdout.write(cleaned)
        return 0
    return emit({
        "message": cleaned,
        "removed": removed,
        "summary": "removed the mention trailer" if removed else "no mention to remove",
    })


def _strip_trailing_mentions(raw: str) -> tuple:
    """(cleaned message, whether removed). Removes only consecutive trailing @mentions (+ surrounding whitespace/newlines)"""
    import re
    cleaned = re.sub(r"\s*(@[A-Za-z0-9_-]+(?:\s+@[A-Za-z0-9_-]+)*)\s*$", "", raw).rstrip()
    return cleaned, raw.rstrip() != cleaned


def _paths_to_add(git, root: str, paths: list) -> list:
    """--paths > git add targets: split values joined by spaces or newlines (zsh `$P`, #1184), exclude already-staged deleted paths (#971)
    Re-adding a staged deleted path stops the whole commit with a pathspec error"""
    split_paths = []
    for value in paths:
        for line in value.splitlines():
            line = line.strip()
            # Split on spaces only when no file by that name exists on disk (keeps real paths with spaces)
            if line and any(character.isspace() for character in line) and not (Path(root) / line).exists():
                split_paths.extend(line.split())
            elif line:
                split_paths.append(line)
    missing = {path for path in split_paths if not (Path(root) / path).exists()}
    if not missing:
        return split_paths
    # Paths relative to the repo root · non-ASCII paths kept verbatim (quotePath off)
    listed = git("-c", "core.quotePath=false", "diff", "--cached", "--name-only", "--relative", "-z").stdout
    already_staged = set(filter(None, listed.split("\0")))
    return [path for path in split_paths if path not in missing or path not in already_staged]


def cmd_commit(args) -> int:
    """Commit in one step: clean the message > stage only the given paths > commit. Never pushes (#940)."""
    import subprocess
    root = args.root or os.getcwd()
    if args.message_file:
        try:
            raw = Path(args.message_file).read_text(encoding="utf-8")
        except OSError as error:
            return emit({"ok": False, "code": "message_file_not_found", "error": str(error)})
    else:
        raw = args.message or ""
    message, removed = _strip_trailing_mentions(raw)
    if not message.strip():
        return emit({"ok": False, "code": "empty_message", "error": "the cleaned commit message is empty",
                     "next": "pass the message with --message-file or --message"})

    def git(*git_args):
        return subprocess.run(["git", "-C", root, *git_args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    to_add = _paths_to_add(git, root, args.paths)
    # .gitignore'd paths (e.g. docs/superpowers/) — add stops everything with "ignored", so point out the cause
    ignored = [line for line in git("check-ignore", "--", *to_add).stdout.splitlines() if line] if to_add else []
    if ignored:
        return emit({"ok": False, "code": "path_ignored", "error": "paths this repo does not track (.gitignore)",
                     "paths": ignored, "next": "remove these paths from --paths and call again"})
    if to_add:
        staged = git("add", "--", *to_add)  # never git add -A: other sessions' changes would mix in
        if staged.returncode != 0:
            return emit({"ok": False, "code": "stage_failed", "error": staged.stderr.strip()[:300],
                         "paths": to_add,
                         "next": ("paths are relative to the repo root. Check spelling and case, and drop paths that are "
                                  "neither on disk nor in the index (such as already committed deletions) from --paths. "
                                  "In zsh pass a path list as ${=P} or one path per argument")})
    if not git("diff", "--cached", "--name-only").stdout.strip():
        return emit({"ok": False, "code": "nothing_staged", "error": "no staged changes",
                     "next": "pass the paths you touched in this task with --paths"})
    done = git("commit", "-m", message)
    if done.returncode != 0:
        return emit({"ok": False, "code": "commit_failed", "error": (done.stderr or done.stdout).strip()[:400],
                     "next": "read the hook or git config error and fix it (do not bypass it with --no-verify)"})
    sha = git("rev-parse", "--short", "HEAD").stdout.strip()
    return emit({"commit": sha, "message": message, "mention_removed": removed,
                 "summary": f"committed {sha}", "next": "push only when the user asks"})


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="commit_cli", description="commit skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gin = sub.add_parser("get-issue-number", help="extract the current issue number from the cwd")
    p_gin.set_defaults(func=cmd_get_issue_number)

    p_gi = sub.add_parser("get-issue", help="get an issue")
    p_gi.add_argument("owner")
    p_gi.add_argument("repo")
    p_gi.add_argument("number", type=int)
    p_gi.set_defaults(func=cmd_get_issue)

    p_nt = sub.add_parser("normalize-title", help="normalize a title")
    p_nt.add_argument("title", nargs="+")
    p_nt.set_defaults(func=cmd_normalize_title)

    p_sm = sub.add_parser("sanitize-message", help="remove the @mention trailer at the end of a commit message")
    p_sm.add_argument("message")
    p_sm.add_argument("--raw", action="store_true", help="print only the cleaned message text instead of JSON")
    p_sm.set_defaults(func=cmd_sanitize_message)

    p_cm = sub.add_parser("commit", help="clean the message, stage only the given paths and commit (no push)")
    p_cm.add_argument("--message-file", dest="message_file", default=None, type=_non_empty_path_arg, help="commit message file")
    p_cm.add_argument("--message", default=None, help="commit message (instead of a file)")
    p_cm.add_argument("--paths", nargs="*", default=[], help="paths touched in this task (omit if already staged)")
    p_cm.add_argument("--root", default=None, type=_non_empty_path_arg, help="repo root (default: cwd)")
    p_cm.set_defaults(func=cmd_commit)

    p_gct = sub.add_parser("get-commit-template", help="commit message template")
    p_gct.add_argument("issue_title")
    p_gct.add_argument("issue_url")
    # When omitted, derived from the title tag. Set it explicitly only when tag and content differ,
    # e.g. the issue is a feature but the actual work is a bug fix.
    p_gct.add_argument("--type", dest="commit_type", default=None, type=_commit_type_arg,
                       help="commit type (fix, docs, chore, ...). Default: inferred from the title tag")
    p_gct.add_argument("--scope", default=None, help="value for the {scope} placeholder")
    p_gct.add_argument("--repo-root", dest="repo_root", default=None, type=_non_empty_path_arg,
                       help="repo root to read the format from (default: git root of the cwd, or the cwd outside git)")
    p_gct.set_defaults(func=cmd_get_commit_template)

    p_rs = sub.add_parser("resolve-style", help="show the commit format and tone (team > personal)")
    p_rs.add_argument("--repo-root", dest="repo_root", default=None, type=_non_empty_path_arg,
                      help="repo root to read the format from (default: git root of the cwd, or the cwd outside git)")
    p_rs.set_defaults(func=cmd_resolve_style)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
