"""rule-docs: facts about rule documents (CLAUDE.md, etc.) > references to missing paths, references to uncommitted paths, wording that invites prose comments, copies of the same document

Path lookup order: the document folder and its ancestors (up to the repo root) > path-suffix match (anywhere in the repo) > bare file name
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .detect import detect_project
from .source_files import git_ignored_paths, walk_files

BACKTICK_PATH_PATTERN = re.compile(r"`([\w.\-]+(?:/[\w.\-]+)+/?|[\w\-]+\.(?:md|py|js|mjs|ts|tsx|dart|java|kt|ya?ml|json|txt|gradle|toml))`")
# Paths inside code blocks (tree diagrams, examples — low confidence, in_code_block tag). A leading $ is an env var placeholder ($HOME/...), so excluded
CODE_BLOCK_PATH_PATTERN = re.compile(r"(?<![\w./$-])((?:[\w.\-]+/)+[\w.\-]*\.(?:md|py|js|ts|tsx|dart|java|kt|ya?ml|json)|(?:[\w.\-]+/){2,})(?![\w/])")
# Wording that invites prose comments (comments should be one-line summaries and step headers — conventions §7)
PROSE_COMMENT_INDUCING_PATTERN = re.compile(
    r"주석\s*(?:은|을|도)?\s*(?:필수|꼭|반드시|자세히|상세히|많이|충분히|풍부)|코드\s*주석\s*필수|"
    r"모든\s*(?:함수|메서드|클래스|파일)에\s*주석|comment\s+(?:every|all|each)|always\s+(?:add|write)\s+comments|"
    r"document\s+every|detailed\s+comments|thoroughly\s+comment",
    re.IGNORECASE,
)
PLACEHOLDER_MARKERS = ("{", "<", "*", "$", "~", "...", "http")
# Extensions tried when matching an extensionless module path (scripts/common/gh_client) to a file
MODULE_EXTENSIONS = (".py", ".js", ".mjs", ".ts", ".tsx", ".dart", ".java", ".kt", ".sh")
MAXIMUM_FINDINGS_PER_DOCUMENT = 30


def inspect_rule_documents(root: Path) -> dict:
    documents = detect_project(root)["rule_documents"]
    all_paths = [relative for relative, _ in walk_files(root)]
    index = _PathIndex(all_paths)
    results, hashes = [], {}
    for relative in documents:
        path = root / relative
        text = path.read_text(encoding="utf-8", errors="replace")
        hashes.setdefault(hashlib.sha256(text.encode("utf-8")).hexdigest(), []).append(relative)
        unresolved, inducing = [], []
        for number, line, is_in_code_block in _lines_with_fence_state(text):
            for reference in _references_in(line, is_in_code_block):
                if not _is_checkable(reference, index) or _exists(root, path.parent, reference, index):
                    continue
                unresolved.append({"line": number, "reference": reference, **({"in_code_block": True} if is_in_code_block else {})})
            if not is_in_code_block and PROSE_COMMENT_INDUCING_PATTERN.search(line):
                inducing.append({"line": number, "text": line.strip()[:200]})
        missing, ignored = _split_ignored(root, path.parent, unresolved)
        results.append({"path": relative, "lines": len(text.splitlines()),
                        "missing_references": missing[:MAXIMUM_FINDINGS_PER_DOCUMENT],
                        "ignored_references": ignored[:MAXIMUM_FINDINGS_PER_DOCUMENT],
                        "prose_comment_inducing": inducing[:MAXIMUM_FINDINGS_PER_DOCUMENT]})
    duplicates = [paths for paths in hashes.values() if len(paths) > 1]
    missing_total = sum(len(r["missing_references"]) for r in results)
    ignored_total = sum(len(r["ignored_references"]) for r in results)
    inducing_total = sum(len(r["prose_comment_inducing"]) for r in results)
    return {"documents": results, "duplicate_documents": duplicates,
            "summary": f"rule documents {len(results)}: missing path references {missing_total}, gitignored path references {ignored_total}, "
                       f"prose-comment inducing {inducing_total}, identical copies {len(duplicates)} groups"}


class _PathIndex:
    """Index of repo file and folder names (for path-suffix matching)"""

    def __init__(self, paths: list):
        self.file_names = {p.rsplit("/", 1)[-1] for p in paths}
        self.paths = paths
        self.directories = set()
        for p in paths:
            parts = p.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                self.directories.add("/".join(parts[:i]))
        self.directory_names = {d.rsplit("/", 1)[-1] for d in self.directories}

    def has_suffix(self, reference: str) -> bool:
        tail = "/" + reference.strip("/")
        if reference.endswith("/"):
            return any(("/" + d).endswith(tail) for d in self.directories)
        return any(("/" + p).endswith(tail) for p in self.paths) or any(("/" + d).endswith(tail) for d in self.directories)


def _lines_with_fence_state(text: str):
    is_in_code_block = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            is_in_code_block = not is_in_code_block
            continue
        yield number, line, is_in_code_block


def _references_in(line: str, is_in_code_block: bool) -> list[str]:
    if is_in_code_block:
        return [m.group(1) for m in CODE_BLOCK_PATH_PATTERN.finditer(line)]
    return [m.group(1) for m in BACKTICK_PATH_PATTERN.finditer(line)]


def _is_checkable(reference: str, index: _PathIndex) -> bool:
    """Whether the path is checkable (placeholders and absolute paths excluded; extensionless a/b only when the first folder exists in the repo — excludes MIME types and import specifiers)"""
    if any(marker in reference for marker in PLACEHOLDER_MARKERS) or reference.startswith("/"):
        return False
    last = reference.rstrip("/").rsplit("/", 1)[-1]
    if not reference.endswith("/") and "." not in last:
        return reference.split("/", 1)[0] in index.directory_names
    return True


def _exists(root: Path, document_directory: Path, reference: str, index: _PathIndex) -> bool:
    """Relative to the document folder and ancestors > path-suffix match > bare file name anywhere in the repo"""
    directory = document_directory
    while True:
        if (directory / reference).exists():
            return True
        if directory == root or root not in directory.parents:
            break
        directory = directory.parent
    if "/" not in reference.rstrip("/"):
        return reference in index.file_names
    if index.has_suffix(reference):
        return True
    last = reference.rsplit("/", 1)[-1]
    return bool(last) and "." not in last and any(index.has_suffix(reference + e) for e in MODULE_EXTENSIONS)


def _split_ignored(root: Path, document_directory: Path, entries: list):
    """Missing paths > (truly missing, gitignored) — checked with git rules relative to both the document folder and the repo root"""
    def candidates(reference):
        relative_to_document = (document_directory / reference).relative_to(root).as_posix() if document_directory != root else reference
        return {reference.rstrip("/"), relative_to_document.rstrip("/")}
    asked = sorted({c for e in entries for c in candidates(e["reference"])})
    ignored_paths = git_ignored_paths(root, asked) or set()
    missing, ignored = [], []
    for entry in entries:
        (ignored if candidates(entry["reference"]) & ignored_paths else missing).append(entry)
    return missing, ignored
