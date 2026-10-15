"""rule-docs: 규칙 문서(CLAUDE.md 등) 사실 > 없는 경로 참조, 줄글 주석 유도 문구"""
from __future__ import annotations

import re
from pathlib import Path

from .detect import detect_project
from .source_files import walk_files

BACKTICK_PATH_PATTERN = re.compile(r"`([\w.\-]+(?:/[\w.\-]+)+/?|[\w\-]+\.(?:md|py|js|mjs|ts|tsx|dart|java|kt|ya?ml|json|txt|gradle|toml))`")
# 줄글 주석을 유도하는 문구 (주석은 한 줄 요약·단계 머리글로 — conventions §7)
PROSE_COMMENT_INDUCING_PATTERN = re.compile(
    r"주석\s*(?:은|을|도)?\s*(?:필수|꼭|반드시|자세히|상세히|많이|충분히|풍부)|코드\s*주석\s*필수|WHY\s*중심|"
    r"모든\s*(?:함수|메서드|클래스|파일)에\s*주석|comment\s+(?:every|all|each)|always\s+(?:add|write)\s+comments|"
    r"document\s+every|detailed\s+comments|thoroughly\s+comment",
    re.IGNORECASE,
)
PLACEHOLDER_MARKERS = ("{", "<", "*", "$", "~", "...", "http")
MAXIMUM_FINDINGS_PER_DOCUMENT = 30


def inspect_rule_documents(root: Path) -> dict:
    documents = detect_project(root)["rule_documents"]
    file_names = {Path(relative).name for relative, _ in walk_files(root)}
    results = []
    for relative in documents:
        path = root / relative
        text = path.read_text(encoding="utf-8", errors="replace")
        missing, inducing = [], []
        for number, line in enumerate(text.splitlines(), start=1):
            for match in BACKTICK_PATH_PATTERN.finditer(line):
                reference = match.group(1)
                if _is_checkable(reference) and not _exists(root, path.parent, reference, file_names):
                    missing.append({"line": number, "reference": reference})
            if PROSE_COMMENT_INDUCING_PATTERN.search(line):
                inducing.append({"line": number, "text": line.strip()[:200]})
        results.append({"path": relative, "lines": len(text.splitlines()),
                        "missing_references": missing[:MAXIMUM_FINDINGS_PER_DOCUMENT],
                        "prose_comment_inducing": inducing[:MAXIMUM_FINDINGS_PER_DOCUMENT]})
    missing_total = sum(len(r["missing_references"]) for r in results)
    inducing_total = sum(len(r["prose_comment_inducing"]) for r in results)
    return {"documents": results,
            "summary": f"규칙 문서 {len(results)}: 없는 경로 참조 {missing_total}, 줄글 주석 유도 {inducing_total}"}


def _is_checkable(reference: str) -> bool:
    return not any(marker in reference for marker in PLACEHOLDER_MARKERS) and not reference.startswith("/")


def _exists(root: Path, document_directory: Path, reference: str, file_names: set) -> bool:
    """문서 폴더 기준 또는 레포 루트 기준 — 맨 파일명은 레포 어디든 있으면 존재로 본다"""
    if (document_directory / reference).exists() or (root / reference).exists():
        return True
    if "/" not in reference.rstrip("/"):
        return reference in file_names
    return False
