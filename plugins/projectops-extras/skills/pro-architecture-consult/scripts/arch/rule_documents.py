"""rule-docs: 규칙 문서(CLAUDE.md 등) 사실 > 없는 경로 참조, 커밋 안 되는 경로 참조, 줄글 주석 유도 문구, 같은 문서 사본

경로 확인 순서: 문서 폴더와 그 조상 폴더(레포 루트까지) > 경로 꼬리 일치(레포 어디든) > 맨 파일명
"""
from __future__ import annotations

import fnmatch
import hashlib
import re
from pathlib import Path

from .detect import detect_project
from .source_files import walk_files

BACKTICK_PATH_PATTERN = re.compile(r"`([\w.\-]+(?:/[\w.\-]+)+/?|[\w\-]+\.(?:md|py|js|mjs|ts|tsx|dart|java|kt|ya?ml|json|txt|gradle|toml))`")
# 코드블록 안 경로 (트리 그림·예시 — 낮은 확신, in_code_block 태그)
CODE_BLOCK_PATH_PATTERN = re.compile(r"(?<![\w./-])((?:[\w.\-]+/)+[\w.\-]*\.(?:md|py|js|ts|tsx|dart|java|kt|ya?ml|json)|(?:[\w.\-]+/){2,})(?![\w/])")
# 줄글 주석을 유도하는 문구 (주석은 한 줄 요약·단계 머리글로 — conventions §7)
PROSE_COMMENT_INDUCING_PATTERN = re.compile(
    r"주석\s*(?:은|을|도)?\s*(?:필수|꼭|반드시|자세히|상세히|많이|충분히|풍부)|코드\s*주석\s*필수|"
    r"모든\s*(?:함수|메서드|클래스|파일)에\s*주석|comment\s+(?:every|all|each)|always\s+(?:add|write)\s+comments|"
    r"document\s+every|detailed\s+comments|thoroughly\s+comment",
    re.IGNORECASE,
)
PLACEHOLDER_MARKERS = ("{", "<", "*", "$", "~", "...", "http")
MAXIMUM_FINDINGS_PER_DOCUMENT = 30


def inspect_rule_documents(root: Path) -> dict:
    documents = detect_project(root)["rule_documents"]
    all_paths = [relative for relative, _ in walk_files(root)]
    index = _PathIndex(all_paths)
    ignore_patterns = _gitignore_patterns(root)
    results, hashes = [], {}
    for relative in documents:
        path = root / relative
        text = path.read_text(encoding="utf-8", errors="replace")
        hashes.setdefault(hashlib.sha256(text.encode("utf-8")).hexdigest(), []).append(relative)
        missing, ignored, inducing = [], [], []
        for number, line, is_in_code_block in _lines_with_fence_state(text):
            for reference in _references_in(line, is_in_code_block):
                if not _is_checkable(reference, index) or _exists(root, path.parent, reference, index):
                    continue
                entry = {"line": number, "reference": reference, **({"in_code_block": True} if is_in_code_block else {})}
                (ignored if _is_ignored(reference, ignore_patterns) else missing).append(entry)
            if not is_in_code_block and PROSE_COMMENT_INDUCING_PATTERN.search(line):
                inducing.append({"line": number, "text": line.strip()[:200]})
        results.append({"path": relative, "lines": len(text.splitlines()),
                        "missing_references": missing[:MAXIMUM_FINDINGS_PER_DOCUMENT],
                        "ignored_references": ignored[:MAXIMUM_FINDINGS_PER_DOCUMENT],
                        "prose_comment_inducing": inducing[:MAXIMUM_FINDINGS_PER_DOCUMENT]})
    duplicates = [paths for paths in hashes.values() if len(paths) > 1]
    missing_total = sum(len(r["missing_references"]) for r in results)
    ignored_total = sum(len(r["ignored_references"]) for r in results)
    inducing_total = sum(len(r["prose_comment_inducing"]) for r in results)
    return {"documents": results, "duplicate_documents": duplicates,
            "summary": f"규칙 문서 {len(results)}: 없는 경로 참조 {missing_total}, gitignore 경로 참조 {ignored_total}, "
                       f"줄글 주석 유도 {inducing_total}, 같은 내용 사본 {len(duplicates)}묶음"}


class _PathIndex:
    """레포 파일·폴더 이름 색인 (꼬리 일치 검사용)"""

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
    """확인할 수 있는 경로인가 (자리표시자·절대경로 제외, 확장자 없는 a/b 는 첫 폴더가 레포에 있을 때만 — MIME·import 지정자 제외)"""
    if any(marker in reference for marker in PLACEHOLDER_MARKERS) or reference.startswith("/"):
        return False
    last = reference.rstrip("/").rsplit("/", 1)[-1]
    if not reference.endswith("/") and "." not in last:
        return reference.split("/", 1)[0] in index.directory_names
    return True


def _exists(root: Path, document_directory: Path, reference: str, index: _PathIndex) -> bool:
    """문서 폴더와 조상 폴더 기준 > 경로 꼬리 일치 > 맨 파일명은 레포 어디든"""
    directory = document_directory
    while True:
        if (directory / reference).exists():
            return True
        if directory == root or root not in directory.parents:
            break
        directory = directory.parent
    if "/" not in reference.rstrip("/"):
        return reference in index.file_names
    return index.has_suffix(reference)


def _gitignore_patterns(root: Path) -> list[str]:
    patterns = []
    for relative, absolute in walk_files(root):
        if absolute.name != ".gitignore":
            continue
        try:
            lines = absolute.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        patterns += [line.strip().lstrip("/") for line in lines if line.strip() and not line.startswith(("#", "!"))]
    return patterns


def _is_ignored(reference: str, patterns: list[str]) -> bool:
    name = reference.rstrip("/").rsplit("/", 1)[-1]
    candidates = (reference, reference.rstrip("/"), name)
    return any(fnmatch.fnmatch(c, p.rstrip("/")) or fnmatch.fnmatch(c, p.rstrip("/") + "/*") for p in patterns for c in candidates)
