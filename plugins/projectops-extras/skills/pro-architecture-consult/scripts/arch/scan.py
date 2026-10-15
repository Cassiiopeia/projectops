"""scan: 파일별 냄새 사실 수집 > 범주별 목록 + 요약 수치 (판정 없음)"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import code_smells
from .source_files import classify_lines, comment_blocks, iter_source_files

# 파일 줄 수 한도 (300 분리 검토, 500 반드시 분리 — conventions §3.3)
REVIEW_SPLIT_LINES = 300
MUST_SPLIT_LINES = 500

CATEGORIES = (
    "long_files", "comment_heavy_files", "long_comment_blocks", "history_comments",
    "banner_comments", "prose_ending_comments", "boolean_names", "boolean_functions", "abbreviations",
    "meaningless_names", "file_type_mismatch", "hardcoded_tokens", "swallowed_catch",
)


def scan_project(root: Path, limit: int) -> dict:
    findings = {category: [] for category in CATEGORIES}
    files_by_language: dict[str, int] = {}
    files_scanned = 0

    # 파일별 수집
    for relative, language, text in iter_source_files(root):
        files_scanned += 1
        files_by_language[language] = files_by_language.get(language, 0) + 1
        _collect_file(relative, language, text, findings)

    # 정렬 (심한 것 먼저) > 상한 적용, 잘린 범주는 전체 수를 남긴다
    findings["long_files"].sort(key=lambda f: -f["lines"])
    findings["comment_heavy_files"].sort(key=lambda f: -(f["comment_lines"] - f["code_lines"]))
    findings["long_comment_blocks"].sort(key=lambda f: -f["length"])
    summary = {category: len(items) for category, items in findings.items()}
    summary["must_split_files"] = sum(1 for f in findings["long_files"] if f["lines"] > MUST_SPLIT_LINES)
    truncated = {c: n for c, n in summary.items() if c in findings and n > limit}
    limited = {category: items[:limit] for category, items in findings.items()}

    return {
        "root": str(root),
        "files_scanned": files_scanned,
        "files_by_language": files_by_language,
        "summary": summary,
        "findings": limited,
        "truncated": truncated,
        "summary_text": _summary_text(files_scanned, summary),
    }


def record_metrics(root: Path, summary: dict, rule_counts: dict) -> Path:
    """docs/architecture/metrics.jsonl 에 한 줄 추가 (추이 비교용)"""
    path = root / "docs" / "architecture" / "metrics.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"date": date.today().isoformat(), "summary": summary, "rules": rule_counts}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    return path


def _collect_file(relative: str, language: str, text: str, findings: dict) -> None:
    classified = classify_lines(text, language)
    total_lines = len(classified)
    comment_lines = sum(1 for _, kind, _ in classified if kind == "comment")
    code_lines = sum(1 for _, kind, _ in classified if kind == "code")

    # 크기·주석 비율
    if total_lines > REVIEW_SPLIT_LINES:
        findings["long_files"].append({"path": relative, "lines": total_lines})
    if code_lines and comment_lines > code_lines:
        findings["comment_heavy_files"].append(
            {"path": relative, "comment_lines": comment_lines, "code_lines": code_lines})
    for start, length, _ in comment_blocks(classified):
        if length >= code_smells.LONG_COMMENT_BLOCK_LINES:
            findings["long_comment_blocks"].append({"path": relative, "line": start, "length": length})

    # 줄 단위: 주석 문구, 이름, 토큰
    lines = text.splitlines()
    for number, kind, content in classified:
        if content:
            for phrase_kind in code_smells.comment_phrase_findings(content):
                findings[f"{phrase_kind}_comments"].append(
                    {"path": relative, "line": number, "text": content[:160]})
        if kind != "code":
            continue
        line = lines[number - 1]
        for name in code_smells.boolean_names_in_line(line, language):
            findings["boolean_names"].append({"path": relative, "line": number, "name": name})
        for name in code_smells.boolean_function_names_in_line(line, language):
            findings["boolean_functions"].append({"path": relative, "line": number, "name": name})
        for finding_kind, name, word in code_smells.naming_findings_in_line(line):
            target = "abbreviations" if finding_kind == "abbreviation" else "meaningless_names"
            findings[target].append({"path": relative, "line": number, "name": name, "word": word})
        for token_kind in code_smells.hardcoded_tokens_in_line(line, language, relative):
            findings["hardcoded_tokens"].append({"path": relative, "line": number, "kind": token_kind})

    # 파일 단위: 타입명, 삼키는 catch
    mismatched_type = code_smells.file_type_name_mismatch(relative, language, text)
    if mismatched_type:
        findings["file_type_mismatch"].append({"path": relative, "first_type": mismatched_type})
    for number in code_smells.swallowed_catch_lines(text, language):
        findings["swallowed_catch"].append({"path": relative, "line": number})


def _summary_text(files_scanned: int, summary: dict) -> str:
    return (f"{files_scanned}개 파일: 300줄 초과 {summary['long_files']}"
            f"(500줄 초과 {summary['must_split_files']}), 주석>코드 {summary['comment_heavy_files']}, "
            f"긴 주석 블록 {summary['long_comment_blocks']}, 경위 주석 {summary['history_comments']}, "
            f"boolean 이름 {summary['boolean_names']}, 약어 {summary['abbreviations']}, "
            f"하드코딩 토큰 {summary['hardcoded_tokens']}")
