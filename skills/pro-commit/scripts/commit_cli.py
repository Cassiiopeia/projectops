#!/usr/bin/env python3
"""commit_cli — commit skill 전용 CLI.

브랜치명 → 이슈 번호 추출, 이슈 제목 조회, 커밋 템플릿 생성.
서브커맨드: get-issue-number, get-issue, normalize-title, get-commit-template,
resolve-style, sanitize-message, commit

사용법:
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
            "html_url": issue["url"],  # 에이전트가 GitHub 원본 키 이름으로 짐작하는 별칭
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


def _style(args) -> tuple:
    """개인 preferences + 팀 version.yml 을 합쳐 커밋 형식을 정한다."""
    from common.commit_style import resolve_for_repo
    return resolve_for_repo(getattr(args, "repo_root", None))


def cmd_resolve_style(args) -> int:
    from common.commit_style import _toplevel
    from common.repo_language import read_team_language
    prefs, style = _style(args)
    v = prefs["values"]
    # 말 언어: 개인 설정 > 팀 version.yml language (#977) > 없음(기본 동작)
    team_language = read_team_language(getattr(args, "repo_root", None) or _toplevel())
    language = v.get("language") or team_language
    language_source = "preferences" if v.get("language") else ("version.yml" if team_language else None)
    return emit({**style, "language": language, "language_source": language_source, "tone": v.get("tone"),
                 "rules": v.get("rules", []), "examples": v.get("examples", []),
                 "ignored": prefs["ignored"], "summary": f"{style['preset']} ({style['source']})"})


def cmd_get_commit_template(args) -> int:
    from common.commit_style import render_for_issue
    _, style = _style(args)
    # 타입 생략 시 팀 commit_type_map 까지 반영 — 이슈 헬퍼 댓글과 같은 타입이 나오게
    template = render_for_issue(style, issue_title=args.issue_title, issue_url=args.issue_url,
                                commit_type=getattr(args, "commit_type", None),
                                scope=getattr(args, "scope", None) or "")
    return emit({"template": template, "source": style["source"], "warnings": style["warnings"],
                 "summary": template})


def cmd_sanitize_message(args) -> int:
    """커밋 메시지 끝의 @mention trailer를 제거한다 (AI 흔적 방지 최후 방어선).

    왜 파이썬인가 — 과거 이 로직은 셸 sed 한 줄이었는데 `:a;$!N;$!ba` 라벨 구문이
    GNU sed 전용이라 macOS(BSD sed)에서 **종료 코드 0으로 조용히 통과**하며
    입력을 그대로 흘려보냈다. 안전망이 켜져 있다고 믿는 상태에서 실제로는 꺼져 있었다.
    OS별 도구 구현 차이를 타지 않도록 파이썬으로 옮겼다 (#523).

    본문 어디에 있든이 아니라 **끝에 붙은** mention만 제거한다 —
    "@projectops build app 관련 수정" 처럼 본문에 의미 있게 등장한 mention은 보존해야 한다.
    """
    cleaned, removed = _strip_trailing_mentions(args.message)
    if getattr(args, "raw", False):
        # 셸이 JSON 을 풀지 않아도 되게 정리된 메시지만 그대로 (#940)
        sys.stdout.write(cleaned)
        return 0
    return emit({
        "message": cleaned,
        "removed": removed,
        "summary": "removed the mention trailer" if removed else "no mention to remove",
    })


def _strip_trailing_mentions(raw: str) -> tuple:
    """(정리된 메시지, 제거했는지). 끝에 연속으로 붙은 @mention 들 (+ 그 앞뒤 공백/개행)만 제거"""
    import re
    cleaned = re.sub(r"\s*(@[A-Za-z0-9_-]+(?:\s+@[A-Za-z0-9_-]+)*)\s*$", "", raw).rstrip()
    return cleaned, raw.rstrip() != cleaned


def _paths_to_add(git, root: str, paths: list) -> list:
    """--paths > git add 대상: 줄바꿈으로 이어진 값 분리, 이미 스테이징된 삭제 경로 제외

    스테이징된 삭제(`git rm`·`git mv` 의 옛 경로)를 다시 add 하면 pathspec 오류로 커밋 전체가 멈춘다 (#971)
    """
    split_paths = [line.strip() for value in paths for line in value.splitlines() if line.strip()]
    missing = {path for path in split_paths if not (Path(root) / path).exists()}
    if not missing:
        return split_paths
    # 레포 루트 기준 상대경로 · 한글 경로 원문 그대로 (quotePath 끔)
    listed = git("-c", "core.quotePath=false", "diff", "--cached", "--name-only", "--relative", "-z").stdout
    already_staged = set(filter(None, listed.split("\0")))
    return [path for path in split_paths if path not in missing or path not in already_staged]


def cmd_commit(args) -> int:
    """커밋 한 번에: 메시지 정리 > 내가 지정한 경로만 스테이징 > 커밋. push 는 하지 않는다 (#940)."""
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
    # .gitignore 대상 경로 (예: docs/superpowers/) — add 가 "ignored" 로 전체를 멈추므로 원인을 짚어 준다
    ignored = [line for line in git("check-ignore", "--", *to_add).stdout.splitlines() if line] if to_add else []
    if ignored:
        return emit({"ok": False, "code": "path_ignored", "error": "paths this repo does not track (.gitignore)",
                     "paths": ignored, "next": "remove these paths from --paths and call again"})
    if to_add:
        staged = git("add", "--", *to_add)  # git add -A 는 쓰지 않는다: 다른 세션의 변경이 섞인다
        if staged.returncode != 0:
            return emit({"ok": False, "code": "stage_failed", "error": staged.stderr.strip()[:300],
                         "paths": to_add,
                         "next": ("paths are relative to the repo root. Check spelling and case, and drop paths that are "
                                  "neither on disk nor in the index (such as already committed deletions) from --paths")})
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
    p_cm.add_argument("--message-file", dest="message_file", default=None, help="commit message file")
    p_cm.add_argument("--message", default=None, help="commit message (instead of a file)")
    p_cm.add_argument("--paths", nargs="*", default=[], help="paths touched in this task (omit if already staged)")
    p_cm.add_argument("--root", default=None, help="repo root (default: cwd)")
    p_cm.set_defaults(func=cmd_commit)

    p_gct = sub.add_parser("get-commit-template", help="commit message template")
    p_gct.add_argument("issue_title")
    p_gct.add_argument("issue_url")
    # 생략하면 제목 태그에서 유도한다. 이슈는 기능인데 실제 작업이 버그 수정인
    # 경우처럼 태그와 내용이 다를 때만 직접 지정한다.
    p_gct.add_argument("--type", dest="commit_type", default=None, type=_commit_type_arg,
                       help="commit type (fix, docs, chore, ...). Default: inferred from the title tag")
    p_gct.add_argument("--scope", default=None, help="value for the {scope} placeholder")
    p_gct.add_argument("--repo-root", dest="repo_root", default=None,
                       help="repo root to read the format from (default: git root of the cwd, or the cwd outside git)")
    p_gct.set_defaults(func=cmd_get_commit_template)

    p_rs = sub.add_parser("resolve-style", help="show the commit format and tone (team > personal)")
    p_rs.add_argument("--repo-root", dest="repo_root", default=None,
                      help="repo root to read the format from (default: git root of the cwd, or the cwd outside git)")
    p_rs.set_defaults(func=cmd_resolve_style)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
