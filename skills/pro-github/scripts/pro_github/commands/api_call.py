"""api: vetted pass-through for GitHub REST calls with no dedicated subcommand (#939).

When a feature is missing, the agent reads the PAT from the config file and calls curl itself. This adds auth in one place,
never prints the PAT, and blocks paths outside the repo and unintended writes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common.emit import emit
from common.gh_client import GitHubAPIError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat

READ_METHODS = ("GET",)
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
# Do not load the whole response into the session even when it is long
MAX_RESPONSE_CHARS = 20000
# Outside the repo but allowed read-only (remaining rate limit check)
READ_ONLY_GLOBAL_PATHS = ("/rate_limit",)
# Repo admin paths where writes are blocked (visibility, delete, transfer, secrets, permissions) — avoids hard-to-undo accidents via the pass-through
REPOSITORY_ADMIN_SUBPATHS = ("transfer", "actions/secrets", "collaborators", "keys", "hooks")
# Repo creation REST paths: /orgs/{org}/repos · /user/repos (group 1: org, None for the user path)
REPOSITORY_CREATION_PATH_PATTERN = re.compile(r"^/(?:orgs/([^/]+)|user)/repos/?$")


def resolve_api_path(owner: str, repo: str, path: str) -> str:
    """Relative path (actions/runs) > /repos/{owner}/{repo}/actions/runs. Absolute paths stay as is"""
    if path.startswith("/"):
        return path
    return f"/repos/{owner}/{repo}/{path}"


def is_path_in_scope(method: str, path: str, prefix: str) -> bool:
    """Only paths under this repo, or allowed global paths called with GET"""
    if ".." in path or "://" in path:
        return False
    if method in READ_METHODS and path.split("?", 1)[0] in READ_ONLY_GLOBAL_PATHS:
        return True
    return path.startswith(prefix)


def is_repository_admin_write(method: str, path: str, prefix: str) -> bool:
    """Whether this edits/deletes the repo itself (/repos/o/r) or writes an admin path"""
    if method not in WRITE_METHODS:
        return False
    bare = path.split("?", 1)[0]
    if bare.rstrip("/") == prefix.rstrip("/"):
        return True
    rest = bare[len(prefix):] if bare.startswith(prefix) else ""
    return any(rest == sub or rest.startswith(sub + "/") for sub in REPOSITORY_ADMIN_SUBPATHS)


def fit_response_data(data, max_chars: int = MAX_RESPONSE_CHARS) -> tuple:
    """Fit the response within the limit as valid JSON > (trimmed data, dropped item count | None=cannot trim).

    For a list, drop items from the end; for an object, drop from the end of its largest list value.
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

    # Maximum item count that fits the limit (binary search)
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
                     "next": _repository_admin_next(args, method, path, prefix)})
    # Reject paths outside the target repo (other repos, users, orgs) — keeps the pass-through from becoming a general token runner
    if not is_path_in_scope(method, path, prefix):
        return emit({"ok": False, "code": "path_out_of_scope",
                     "error": f"the path must start with {prefix} (read-only exception: GET /rate_limit): {args.path}",
                     "next": _out_of_scope_next(args, method, path)})
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
        # With --out, receive bytes — also saves non-JSON responses such as artifact zips and zipballs (#987)
        data = api._request(method, f"https://api.github.com{path}", payload, pat, as_bytes=bool(args.out))
    except GitHubAPIError as e:
        return api_error(e)
    if isinstance(data, bytes):
        data, is_json = _parse_json_bytes(data)
        if not is_json:
            return _emit_binary_saved(args, method, path, data)
    return _emit_api_result(args, method, path, data)


def _repository_admin_next(args, method: str, path: str, prefix: str) -> str:
    """Blocked repo admin write > dedicated command when one fits (visibility-only PATCH, DELETE of the repo, #1241)"""
    is_repository_root = path.split("?", 1)[0].rstrip("/") == prefix.rstrip("/")
    if is_repository_root and method == "DELETE":
        return f"delete-repo {args.owner} {args.repo} --dry-run (deleting then needs --confirm {args.owner}/{args.repo})"
    if is_repository_root and method == "PATCH" and _is_visibility_only_body(args.body_file):
        return f"update-repo {args.owner} {args.repo} --visibility public|private --dry-run"
    return "use secrets set for secrets; update-repo for visibility; the user changes other repo settings in the GitHub UI"


def _is_visibility_only_body(body_file: str | None) -> bool:
    """Body file holds only private and/or visibility (unreadable or empty > False)"""
    if not body_file:
        return False
    try:
        payload = json.loads(Path(body_file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(payload, dict) and bool(payload) and set(payload) <= {"private", "visibility"}


def _out_of_scope_next(args, method: str, path: str) -> str:
    """Out-of-scope path > next-command hint (for repo creation paths, the dedicated create-repo command, #1022)"""
    creation_match = REPOSITORY_CREATION_PATH_PATTERN.match(path.split("?", 1)[0])
    if method == "POST" and creation_match:
        repository_owner = creation_match.group(1) or args.owner
        return f"create-repo {repository_owner} <name> [--private] [--description D] [--auto-init] [--dry-run]"
    return f"use a path relative to this repo, e.g. api GET {args.owner} {args.repo} issues/1"


def _parse_json_bytes(content: bytes):
    """Response bytes > (JSON value, True) | (raw bytes, False). Empty body stays {} as before"""
    if not content:
        return {}, True
    try:
        return json.loads(content.decode("utf-8")), True
    except (UnicodeDecodeError, ValueError):
        return content, False


def _emit_binary_saved(args, method: str, path: str, content: bytes) -> int:
    """Non-JSON response > save raw bytes to --out, body not included in the response"""
    saved_path = Path(args.out)
    saved_path.write_bytes(content)
    return emit({"method": method, "path": path, "binary": True, "bytes": len(content),
                 "saved_to": str(saved_path.resolve()), "truncated": False,
                 "summary": f"{method} {path} done (binary response, {len(content)} bytes saved)"})


def _emit_api_result(args, method: str, path: str, data) -> int:
    """Save everything (--out) > fit the limit > if trimmed, hint per_page·--out"""
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
    parser.add_argument("--out", default=None, help="save the full response to this file: JSON as-is, non-JSON (zip, artifacts) as raw bytes with binary: true (the data in the reply is trimmed to the size limit)")
    parser.add_argument("--write", action="store_true", help="allow POST, PUT, PATCH, DELETE (only when the user asked for the change)")


COMMANDS = [
    Command(name="api", help="pass-through for REST calls with no dedicated command (this repo only; writes need --write; to create a repo use create-repo)",
            run=cmd_api, configure=_configure_api),
]
