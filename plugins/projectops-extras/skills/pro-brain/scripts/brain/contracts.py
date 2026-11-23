"""Contract changes from a diff, names only: API endpoints, DB migrations, config keys, env or secret names, feature flags
Heuristic on changed paths and +/- lines; values are never read out, so a secret's value can never reach a note.
"""
from __future__ import annotations

import re
from pathlib import Path

from .repo_facts import GitError, run_git

NAME_LIMIT = 12                    # entries kept per contract kind
DIFF_CHARACTER_LIMIT = 2_000_000   # stop reading a huge diff (generated files, lock files)

# Migration files: Flyway V1__x.sql, Liquibase changelogs, Rails/Django/Alembic/Prisma/Knex migration folders
MIGRATION_PATH = re.compile(r"(^|/)(db/migration|migrations?|alembic/versions|prisma/migrations|changelog)(/|$)"
                            r"|(^|/)V\d+[\w.]*__[\w-]+\.sql$", re.IGNORECASE)
# Config files whose keys are contracts between code and deployment
CONFIG_PATH = re.compile(r"(^|/)(application[\w-]*\.(ya?ml|properties)|settings[\w-]*\.(py|ya?ml|toml)"
                         r"|config[\w-]*\.(ya?ml|json|toml)|version\.yml|app\.json|pubspec\.yaml)$", re.IGNORECASE)
# OpenAPI documents: a changed "/path": { key is a changed endpoint
OPENAPI_PATH = re.compile(r"(^|/)(openapi|swagger)[\w.-]*\.(json|ya?ml)$", re.IGNORECASE)
OPENAPI_PATH_KEY = re.compile(r"^\s*[\"']?(/[^\"':\s]*)[\"']?\s*:\s*\{?\s*$")
ENV_EXAMPLE_PATH = re.compile(r"(^|/)\.env[\w.-]*$", re.IGNORECASE)
SOURCE_SKIP_PATH = re.compile(r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|Podfile\.lock|.*\.min\.js)$")

ROUTE_PATTERNS = (
    # Spring: @GetMapping("/x"), @RequestMapping(value = "/x", method = POST)
    re.compile(r"@(Get|Post|Put|Delete|Patch|Request)Mapping\(\s*(?:value\s*=\s*|path\s*=\s*)?\{?\s*\"([^\"]+)\""),
    # FastAPI / Flask: @router.get("/x"), @app.post("/x"), @bp.route("/x")
    re.compile(r"@\w+\.(get|post|put|delete|patch|route)\(\s*[\"']([^\"']+)[\"']"),
    # Express / Koa: router.get('/x', ...), app.post("/x", ...)
    re.compile(r"\b(?:router|app|api)\.(get|post|put|delete|patch)\(\s*[\"'`](/[^\"'`]*)[\"'`]"),
)
ENV_NAME_PATTERNS = (
    re.compile(r"\$\{\{\s*secrets\.([A-Z][A-Z0-9_]+)"),                       # GitHub Actions secrets
    re.compile(r"\$\{\{\s*vars\.([A-Z][A-Z0-9_]+)"),
    re.compile(r"\$\{([A-Z][A-Z0-9_]{2,})(?::[^}]*)?\}"),                      # ${DB_URL:default} in Spring / shell
    re.compile(r"os\.(?:environ(?:\.get)?|getenv)\(?\[?\s*[\"']([A-Z][A-Z0-9_]+)[\"']"),
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]+)"),
    re.compile(r"System\.getenv\(\s*\"([A-Z][A-Z0-9_]+)\""),
    re.compile(r"String\.fromEnvironment\(\s*[\"']([A-Z][A-Z0-9_]+)[\"']"),   # Dart --dart-define
)
FEATURE_FLAG_PATTERNS = (
    re.compile(r"\b((?:FEATURE|FF)_[A-Z0-9_]{2,})\b"),
    re.compile(r"(?:isFeatureEnabled|isEnabled|featureFlag|feature_flag|isFlagOn)\(\s*[\"']([\w.-]+)[\"']"),
)
CONFIG_KEY_LINE = re.compile(r"^\s*([A-Za-z_][\w.-]*)\s*[:=]")
YAML_SUFFIXES = (".yml", ".yaml")
HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
# Spring class-level prefix: @RequestMapping("/api/x") right before the class declaration
CLASS_PREFIX = re.compile(r"@RequestMapping\(\s*(?:value\s*=\s*|path\s*=\s*)?\{?\s*\"([^\"]+)\"[^)]*\)\s*(?:@\w+(?:\([^)]*\))?\s*)*"
                          r"(?:public\s+|abstract\s+|final\s+|open\s+|internal\s+)*(?:class|interface)\s")
ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]+)\s*=")


def _diff_text(repo_root: Path, commit_range: dict) -> str:
    """Unified diff with no context for the range (only the matched commits in issue/commit-list modes)"""
    try:
        if commit_range["mode"] in ("issue-commits", "commit-list"):
            chunks, size = [], 0
            for sha in commit_range["commits"]:
                chunk = run_git(repo_root, "show", "--format=", "-U0", "--no-color", sha)
                chunks.append(chunk)
                size += len(chunk)
                if size > DIFF_CHARACTER_LIMIT:
                    break
            return "\n".join(chunks)
        return run_git(repo_root, "diff", "-U0", "--no-color", commit_range["base"], commit_range["head"])[:DIFF_CHARACTER_LIMIT]
    except GitError:
        return ""


def _changed_lines_by_file(diff_text: str, knowledge_prefix: str) -> dict[str, list[tuple[str, str, int]]]:
    """path > (sign, line, line number in the old or new file); knowledge notes and lock files left out"""
    lines_by_file: dict[str, list[tuple[str, str, int]]] = {}
    current, in_header, old_number, new_number = None, False, 0, 0
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current, in_header = None, True   # header lines (---/+++/index) until the first hunk
            continue
        hunk = HUNK_HEADER.match(line)
        if in_header and not hunk:
            if line.startswith("+++ "):
                path = line[4:].strip()
                current = current if path == "/dev/null" else re.sub(r"^b/", "", path)
            elif line.startswith("--- ") and current is None:
                path = line[4:].strip()
                current = None if path == "/dev/null" else re.sub(r"^a/", "", path)   # deleted file keeps its old name
            continue
        if hunk:
            if in_header and current and (current.startswith(knowledge_prefix) or SOURCE_SKIP_PATH.search(current)):
                current = None
            in_header, old_number, new_number = False, int(hunk.group(1)), int(hunk.group(2))
            continue
        if current and line[:1] == "+":
            lines_by_file.setdefault(current, []).append(("+", line[1:], new_number))
            new_number += 1
        elif current and line[:1] == "-":
            lines_by_file.setdefault(current, []).append(("-", line[1:], old_number))
            old_number += 1
    return lines_by_file


def _file_at(repo_root: Path, ref: str, path: str) -> str:
    try:
        return run_git(repo_root, "show", f"{ref}:{path}")
    except GitError:
        return ""


def _yaml_key_paths(text: str) -> dict[int, str]:
    """line number > dotted key path for YAML lines that carry a value (parents without a value are left out)"""
    paths, stack = {}, []
    for number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^(\s*)([A-Za-z_][\w.-]*):(.*)$", line)
        if not match or line.lstrip().startswith("#"):
            continue
        indent = len(match.group(1))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, match.group(2)))
        value = re.sub(r"\s+#.*$", "", match.group(3)).strip()
        if value:
            paths[number] = ".".join(key for _, key in stack)
    return paths


def _spring_prefix(repo_root: Path, ref: str, path: str) -> str | None:
    if not path.endswith((".java", ".kt")):
        return None
    match = CLASS_PREFIX.search(_file_at(repo_root, ref, path))
    return match.group(1).rstrip("/") if match else None


def _add(bucket: list[str], name: str) -> None:
    if name and name not in bucket and len(bucket) < NAME_LIMIT:
        bucket.append(name)


def detect_contract_changes(repo_root: Path, commit_range: dict, changed_paths: list[str], knowledge_path: str) -> dict:
    """{api_endpoints, db_migrations, config_keys, env_or_secret_names, feature_flags}, names only"""
    found = {"api_endpoints": [], "db_migrations": [], "config_keys": [], "env_or_secret_names": [], "feature_flags": []}
    for path in changed_paths:
        if MIGRATION_PATH.search(path) and not path.endswith("/"):
            _add(found["db_migrations"], path.rsplit("/", 1)[-1])
    lines_by_file = _changed_lines_by_file(_diff_text(repo_root, commit_range), knowledge_path.strip("/") + "/")
    for path, lines in lines_by_file.items():
        file_name = path.rsplit("/", 1)[-1]
        is_config = bool(CONFIG_PATH.search(path))
        is_env_example = bool(ENV_EXAMPLE_PATH.search(path))
        is_openapi = bool(OPENAPI_PATH.search(path))
        prefix = _spring_prefix(repo_root, commit_range["head"], path)
        yaml_paths = {}
        if is_config and path.endswith(YAML_SUFFIXES):
            yaml_paths = {"+": _yaml_key_paths(_file_at(repo_root, commit_range["head"], path)),
                          "-": _yaml_key_paths(_file_at(repo_root, commit_range["base"], path))}
        for sign, line, number in lines:
            openapi_match = OPENAPI_PATH_KEY.match(line) if is_openapi else None
            if openapi_match:
                _add(found["api_endpoints"], f"ANY {openapi_match.group(1)}")
            for pattern in ROUTE_PATTERNS:
                for match in pattern.finditer(line):
                    method = match.group(1).upper()
                    if prefix and CLASS_PREFIX.search(line + " class "):
                        continue   # the class-level prefix itself, folded into the method routes below
                    method = "ANY" if method in ("REQUEST", "ROUTE") else method
                    route = match.group(2)
                    if prefix and not route.startswith(prefix):
                        route = prefix + ("" if route.startswith("/") else "/") + route
                    _add(found["api_endpoints"], f"{method} {route}")
            for pattern in ENV_NAME_PATTERNS:
                for match in pattern.finditer(line):
                    _add(found["env_or_secret_names"], match.group(1))
            for pattern in FEATURE_FLAG_PATTERNS:
                for match in pattern.finditer(line):
                    _add(found["feature_flags"], match.group(1))
            if is_env_example:
                env_match = ENV_LINE.match(line)
                if env_match:
                    _add(found["env_or_secret_names"], env_match.group(1))   # name only, the value after = is dropped
            elif yaml_paths:
                key_path = yaml_paths[sign].get(number)
                if key_path:
                    _add(found["config_keys"], f"{file_name}:{key_path}")
            elif is_config:
                key_match = CONFIG_KEY_LINE.match(line)
                if key_match and not line.lstrip().startswith(("#", "//", "-")):
                    _add(found["config_keys"], f"{file_name}:{key_match.group(1)}")
    return found
