"""api: 전용 서브커맨드가 없는 GitHub REST 호출의 검증된 통과 경로 (#939).

기능이 비면 에이전트가 설정 파일에서 PAT 를 읽어 curl 을 직접 쓴다. 인증을 여기서 한 곳에서 붙이고
PAT 를 출력하지 않으며, 레포 범위 밖 경로와 의도하지 않은 쓰기를 막는다.
"""
from __future__ import annotations

import json
from pathlib import Path

from common.emit import emit
from common.gh_client import GitHubAPIError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat

READ_METHODS = ("GET",)
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
# 응답이 길어도 세션에 다 싣지 않는다
MAX_RESPONSE_CHARS = 20000


def cmd_api(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    method = args.method.upper()
    prefix = f"/repos/{args.owner}/{args.repo}/"
    if method not in READ_METHODS + WRITE_METHODS:
        return emit({"ok": False, "code": "bad_argument", "error": f"지원하지 않는 메서드: {method}"})
    # 대상 레포 밖 경로(다른 레포·사용자·조직)는 거절 — 통과 경로가 범용 토큰 사용기가 되지 않게
    if not args.path.startswith(prefix) or ".." in args.path or "://" in args.path:
        return emit({"ok": False, "code": "path_out_of_scope",
                     "error": f"경로는 {prefix} 로 시작해야 한다: {args.path}",
                     "next": f"api GET {prefix}issues/1 처럼 이 레포 아래 경로만 쓴다"})
    if method in WRITE_METHODS and not args.write:
        return emit({"ok": False, "code": "write_requires_flag",
                     "error": f"{method} 는 상태를 바꾼다. 사용자가 요청한 작업일 때만 --write 를 붙인다",
                     "next": "전용 서브커맨드가 있으면 그것을 쓴다 (list-prs, actions dispatch 등)"})
    payload = None
    if args.body_file:
        try:
            payload = json.loads(Path(args.body_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return emit({"ok": False, "code": "body_file_invalid", "error": f"{args.body_file}: {error}"})
    try:
        data = api._request(method, f"https://api.github.com{args.path}", payload, pat)
    except GitHubAPIError as e:
        return api_error(e)
    text = json.dumps(data, ensure_ascii=False)
    truncated = len(text) > MAX_RESPONSE_CHARS
    return emit({"method": method, "path": args.path,
                 "data": data if not truncated else text[:MAX_RESPONSE_CHARS], "truncated": truncated,
                 "summary": f"{method} {args.path} 완료"})


def _configure_api(parser) -> None:
    parser.add_argument("method", help="GET · POST · PUT · PATCH · DELETE")
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("path", help="/repos/{owner}/{repo}/ 아래의 REST 경로 (예: /repos/o/r/releases/latest)")
    parser.add_argument("--body-file", dest="body_file", default=None, help="JSON 본문 파일")
    parser.add_argument("--write", action="store_true", help="POST·PUT·PATCH·DELETE 허용 (사용자가 요청한 작업일 때만)")


COMMANDS = [
    Command(name="api", help="전용 명령이 없는 REST 호출 통과 (이 레포 경로만, 쓰기는 --write)",
            run=cmd_api, configure=_configure_api),
]
