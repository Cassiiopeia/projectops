"""Shared source file walking: excluded folders, language detection, comment line classification"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path

# Excluded folders (same list as the 4 rule test templates — ledger verdicts must match)
SKIPPED_DIRECTORY_NAMES = {
    ".git", "build", "dist", "node_modules", ".dart_tool", "Pods", ".gradle",
    "venv", ".venv", "__pycache__", ".next", "out", "target", ".idea",
}

# Generated files (excluded only in scan, deps, diff — not human-written, so not subject to rules)
GENERATED_FILE_PATTERN = re.compile(
    r"(\.g\.dart|\.freezed\.dart|\.gr\.dart|\.mocks\.dart|\.gen\.\w+|\.min\.js|\.pb\.\w+|_pb2\.py)$"
)

LANGUAGE_BY_EXTENSION = {
    ".dart": "dart", ".java": "java", ".kt": "kotlin", ".py": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
}
# Languages the CLI cannot analyze (only file counts are reported — the agent must read samples directly)
NOT_ANALYZED_LANGUAGE_BY_EXTENSION = {
    ".go": "go", ".rs": "rust", ".swift": "swift", ".m": "objective-c", ".mm": "objective-c", ".cs": "csharp",
    ".php": "php", ".rb": "ruby", ".scala": "scala", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp",
    ".hpp": "cpp", ".lua": "lua", ".ex": "elixir", ".exs": "elixir", ".vue": "vue", ".svelte": "svelte",
}
SLASH_COMMENT_LANGUAGES = {"dart", "java", "kotlin", "javascript", "typescript"}

# Max read size per file (2MB — larger files are treated as generated/data and skipped)
MAXIMUM_SOURCE_BYTES = 2 * 1024 * 1024


def walk_files(root: Path, start: Path | None = None):
    """Yield (relative posix path from root, absolute path) pairs (no descent into excluded folders)"""
    base = start or root
    for directory, subdirectories, filenames in os.walk(base):
        subdirectories[:] = sorted(d for d in subdirectories if d not in SKIPPED_DIRECTORY_NAMES)
        for filename in sorted(filenames):
            absolute = Path(directory) / filename
            yield absolute.relative_to(root).as_posix(), absolute


def git_ignored_paths(root: Path, relatives: list) -> set | None:
    """Ignored paths. With git, git check-ignore (exact git rules, including nested .gitignore scopes);
    outside a git repo, approximated with root .gitignore patterns only"""
    if not relatives:
        return set()
    try:
        completed = subprocess.run(["git", "-C", str(root), "check-ignore", "--stdin"], input="\n".join(relatives),
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        # Exit code: 0 at least one ignored, 1 none, 128 not a git repo
        if completed.returncode in (0, 1):
            return {line.strip() for line in completed.stdout.splitlines() if line.strip()}
    except (OSError, subprocess.SubprocessError):
        pass
    return _ignored_by_root_gitignore(root, relatives)


def _ignored_by_root_gitignore(root: Path, relatives: list) -> set:
    try:
        lines = (root / ".gitignore").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return set()
    patterns = [l.strip().lstrip("/").rstrip("/") for l in lines if l.strip() and not l.startswith(("#", "!"))]
    ignored = set()
    for relative in relatives:
        name = relative.rsplit("/", 1)[-1]
        if any(fnmatch.fnmatch(c, p) or fnmatch.fnmatch(c, p + "/*") for p in patterns for c in (relative, name)):
            ignored.add(relative)
    return ignored


def tracked_files(root: Path) -> list:
    """Relative paths of git-tracked files (outside a git repo, all files except excluded folders)"""
    try:
        completed = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=60)
        if completed.returncode == 0:
            return [r for r in completed.stdout.split("\0")
                    if r and not (set(r.split("/")[:-1]) & SKIPPED_DIRECTORY_NAMES)]
    except (OSError, subprocess.SubprocessError):
        pass
    return [relative for relative, _ in walk_files(root)]


def language_of(relative_path: str) -> str | None:
    return LANGUAGE_BY_EXTENSION.get(Path(relative_path).suffix.lower())


def is_generated_file(relative_path: str) -> bool:
    return bool(GENERATED_FILE_PATTERN.search(relative_path))


def iter_source_files(root: Path):
    """Human-written sources only: (relative path, language, content)"""
    for relative, absolute in walk_files(root):
        language = language_of(relative)
        if not language or is_generated_file(relative):
            continue
        try:
            if absolute.stat().st_size > MAXIMUM_SOURCE_BYTES:
                continue
            text = absolute.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        yield relative, language, text


def classify_lines(text: str, language: str):
    """Per line (number, kind, comment text) — kind: comment / code / blank

    2 comment kinds: whole-line comments, block comments (/* */, Python docstrings). Trailing comments count as code; only their text is passed on.
    """
    result = []
    is_inside_block = False
    block_terminator = ""
    block_kind = "comment"
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if is_inside_block:
            result.append((number, block_kind, stripped if block_kind == "comment" else ""))
            if (block_terminator == "*/" and "*/" in stripped) or \
                    (block_terminator != "*/" and stripped.count(block_terminator) % 2 == 1):
                is_inside_block = False
            continue
        if not stripped:
            result.append((number, "blank", ""))
            continue
        if language in SLASH_COMMENT_LANGUAGES:
            if stripped.startswith("//"):
                result.append((number, "comment", stripped))
            elif stripped.startswith("/*"):
                result.append((number, "comment", stripped))
                if "*/" not in stripped[2:]:
                    is_inside_block, block_terminator, block_kind = True, "*/", "comment"
            else:
                result.append((number, "code", _trailing_slash_comment(raw)))
            continue
        # Python: # comments; triple quotes at line start = docstring (comment), other triple quotes = multi-line string (code)
        opened_quote = next((q for q in ('"""', "'''") if stripped.count(q) % 2 == 1), None)
        if stripped.startswith("#") and not stripped.startswith("#!"):
            result.append((number, "comment", stripped))
        elif stripped.startswith(('"""', "'''")):
            result.append((number, "comment", stripped))
            if opened_quote:
                is_inside_block, block_terminator, block_kind = True, opened_quote, "comment"
        else:
            trailing = raw.split("  #", 1)[1].strip() if "  #" in raw and not opened_quote else ""
            result.append((number, "code", trailing))
            if opened_quote:
                is_inside_block, block_terminator, block_kind = True, opened_quote, "code"
    return result


def _trailing_slash_comment(raw: str) -> str:
    """Text of a trailing // comment (// inside strings roughly filtered: URLs excluded)"""
    index = raw.find(" //")
    if index < 0 or "://" in raw[max(0, index - 6):index + 3]:
        return ""
    return raw[index:].strip()


def comment_blocks(classified):
    """Groups of consecutive comment lines: [(start line, length, text list)]"""
    blocks, current = [], []
    for number, kind, content in classified:
        if kind == "comment":
            current.append((number, content))
        elif current:
            blocks.append((current[0][0], len(current), [c for _, c in current]))
            current = []
    if current:
        blocks.append((current[0][0], len(current), [c for _, c in current]))
    return blocks


def split_identifier_words(name: str) -> list[str]:
    """camelCase/PascalCase/snake_case > list of lowercase words"""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name.strip("_$"))
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return [w.lower() for w in re.split(r"[\s_$]+", spaced) if w]


def write_outside_repo(root: Path, out: str, payload: dict) -> dict:
    """Write the full result file (outside the repo only — leaves no byproducts in the repo)"""
    target = Path(out).expanduser().resolve()
    if target == root or root in target.parents:
        return {"ok": False, "code": "out_inside_repo", "summary": f"--out must be outside the repo: {target}",
                "next": "Use ~/.projectops/tmp/ or a scratch folder"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"path": str(target)}
