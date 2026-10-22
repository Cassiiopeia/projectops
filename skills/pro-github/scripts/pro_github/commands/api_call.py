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
# 레포 밖이지만 읽기 전용으로 허용하는 경로 (남은 호출 한도 확인)
READ_ONLY_GLOBAL_PATHS = ("/rate_limit",)
# 쓰기를 막는 레포 관리 경로 (공개 전환·삭제·이전·비밀·권한) — 통과 경로로 되돌리기 어려운 사고를 내지 않게
REPOSITORY_ADMIN_SUBPATHS = ("transfer", "actions/secrets", "collaborators", "keys", "hooks")


def resolve_api_path(owner: str, repo: str, path: str) -> str:
    """상대 경로(actions/runs) > /repos/{owner}/{repo}/actions/runs. 절대 경로는 그대로"""
    if path.startswith("/"):
        return path
    return f"/repos/{owner}/{repo}/{path}"


def is_path_in_scope(method: str, path: str, prefix: str) -> bool:
    """이 레포 아래 경로, 또는 GET 으로 부르는 허용 전역 경로만"""
    if ".." in path or "://" in path:
        return False
    if method in READ_METHODS and path.split("?", 1)[0] in READ_ONLY_GLOBAL_PATHS:
        return True
    return path.startswith(prefix)


def is_repository_admin_write(method: str, path: str, prefix: str) -> bool:
    """레포 자체(/repos/o/r) 수정·삭제 또는 관리 경로 쓰기인지"""
    if method not in WRITE_METHODS:
        return False
    bare = path.split("?", 1)[0]
    if bare.rstrip("/") == prefix.rstrip("/"):
        return True
    rest = bare[len(prefix):] if bare.startswith(prefix) else ""
    return any(rest == sub or rest.startswith(sub + "/") for sub in REPOSITORY_ADMIN_SUBPATHS)


def fit_response_data(data, max_chars: int = MAX_RESPONSE_CHARS) -> tuple:
    """응답을 유효한 JSON 으로 한도 안에 맞춘다 > (줄인 data, 버린 항목 수 | None=줄일 수 없음).

    목록이면 뒤 항목부터, 객체면 가장 큰 목록 값의 뒤 항목부터 버린다.
    """
    if len(json.dumps(data, ensure_ascii=False)) <= max_chars:
        return data, 0
    list_key = None
    if isinstance(data, dict):
        list_values = {key: value for key, value in data.items() if isinstance(value, list) and value}
        if not list_values:
            return None, None
        list_key = max(list_values, key=lambda key: len(json.dumps(list_values[key], ensure_ascii=False)))
        items = list_values[list_key]
    elif isinstance(data, list):
        items = data
    else:
        return None, None

    def rebuild(count: int):
        return items[:count] if list_key is None else {**data, list_key: items[:count]}

    # 한도 안에 드는 최대 항목 수 (이분 탐색)
    low, high = 0, len(items)
    while low < high:
        middle = (low + high + 1) // 2
        if len(json.dumps(rebuild(middle), ensure_ascii=False)) <= max_chars:
            low = middle
        else:
            high = middle - 1
    trimmed = rebuild(low)
    if len(json.dumps(trimmed, ensure_ascii=False)) > max_chars:
        return None, None
    return trimmed, len(items) - low


def cmd_api(args, api) -> int:
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    method = args.method.upper()
    prefix = f"/repos/{args.owner}/{args.repo}/"
    path = resolve_api_path(args.owner, args.repo, args.path)
    if method not in READ_METHODS + WRITE_METHODS:
        return emit({"ok": False, "code": "bad_argument", "error": f"unsupported method: {method}"})
    if is_repository_admin_write(method, path, prefix):
        return emit({"ok": False, "code": "repo_admin_blocked",
                     "error": f"repo settings, deletion, transfer, secrets and permission writes do not go through this pass-through: {method} {path}",
                     "next": "use secrets set for secrets; the user changes repo settings in the GitHub UI"})
    # 대상 레포 밖 경로(다른 레포·사용자·조직)는 거절 — 통과 경로가 범용 토큰 사용기가 되지 않게
    if not is_path_in_scope(method, path, prefix):
        return emit({"ok": False, "code": "path_out_of_scope",
                     "error": f"the path must start with {prefix} (read-only exception: GET /rate_limit): {args.path}",
                     "next": f"use a path relative to this repo, e.g. api GET {args.owner} {args.repo} issues/1"})
    if method in WRITE_METHODS and not args.write:
        return emit({"ok": False, "code": "write_requires_flag",
                     "error": f"{method} changes state. Add --write only when the user asked for this change",
                     "next": "use a dedicated subcommand when one exists (list-prs, actions dispatch, ...)"})
    payload = None
    if args.body_file:
        try:
            payload = json.loads(Path(args.body_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return emit({"ok": False, "code": "body_file_invalid", "error": f"{args.body_file}: {error}"})
    try:
        data = api._request(method, f"https://api.github.com{path}", payload, pat)
    except GitHubAPIError as e:
        return api_error(e)
    return _emit_api_result(args, method, path, data)


def _emit_api_result(args, method: str, path: str, data) -> int:
    """전체 저장(--out) > 한도 맞춤 > 잘렸으면 per_page·--out 안내"""
    out = {"method": method, "path": path, "summary": f"{method} {path} done"}
    if args.out:
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        out["saved_to"] = str(Path(args.out).resolve())
    fitted, dropped_count = fit_response_data(data)
    out["data"] = fitted
    out["truncated"] = dropped_count != 0
    if dropped_count:
        out["truncated_items"] = dropped_count
    if out["truncated"] and not args.out:
        out["summary"] += (f" (response too large; dropped the last {dropped_count} item(s))" if dropped_count
                           else " (response too large; data left out)")
        out["next"] = (f"ask for fewer items with ?per_page=10 on the path, or get everything with "
                       f"api {method} {args.owner} {args.repo} {args.path} --out <file>")
    return emit(out)


def _configure_api(parser) -> None:
    parser.add_argument("method", help="GET · POST · PUT · PATCH · DELETE")
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("path", help="REST path. A relative path (actions/runs) gets /repos/{owner}/{repo}/ prepended. "
                                     "Read-only exception: GET /rate_limit")
    parser.add_argument("--body-file", dest="body_file", default=None, help="JSON body file")
    parser.add_argument("--out", default=None, help="save the full JSON response to this file (the data in the reply is trimmed to the size limit)")
    parser.add_argument("--write", action="store_true", help="allow POST, PUT, PATCH, DELETE (only when the user asked for the change)")


COMMANDS = [
    Command(name="api", help="pass-through for REST calls with no dedicated command (this repo only; writes need --write)",
            run=cmd_api, configure=_configure_api),
]
