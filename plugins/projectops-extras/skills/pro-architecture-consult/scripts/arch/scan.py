"""scan: 레포가 소유한 코드의 냄새 사실 > 범주별 목록 + 판단 단서 (판정 없음)

운영(production)과 테스트(test)를 따로 센다. 도구 설치물·생성물·외부 라이브러리는 excluded 로 수와 이유만 낸다.
정렬·집계·읽는 순서는 scan_report.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from . import code_smells, naming_smells, scan_report, structure_smells
from .origins import SourceInventory
from .source_files import classify_lines, comment_blocks

# 파일 줄 수 한도 (300 분리 검토 — conventions §3.3, 반드시 분리 500 은 scan_report.MUST_SPLIT_LINES)
REVIEW_SPLIT_LINES = 300
# 운영 코드에 섞인 테스트·목 코드 (경로 폴더 이름 또는 파일 이름)
TEST_CODE_DIRECTORY_NAMES = {"test", "tests", "mock", "mocks", "dummy", "fixture", "fixtures", "sample", "samples"}
TEST_CODE_FILE_PATTERN = re.compile(r"^(?:Test|Mock|Dummy|Fake)\w*(?:Controller|Service|Api|Router|Resource)\.\w+$|^(?:mock|dummy|fake)_\w+\.py$")
DECLARATION_ONLY_PATTERN = re.compile(r"\binterface\s+\w+|\babstract\s+class\b|\bdeclare\s+module\b")

PER_FILE_CATEGORIES = scan_report.PER_FILE_CATEGORIES
CROSS_FILE_CATEGORIES = scan_report.CROSS_FILE_CATEGORIES


def scan_project(root: Path, limit: int, is_including_all: bool = False,
                 only_prefixes: list | None = None, categories: list | None = None) -> dict:
    inventory = SourceInventory(root, is_including_all)
    findings = {category: [] for category in PER_FILE_CATEGORIES}
    cross_file_inputs, files_by_origin, files_by_language = [], {}, {}

    # 파일별 수집 (경로 필터는 수집 단계에서 — 하위 에이전트에 그 폴더 사실만 넘기기)
    for relative, language, text, origin in inventory.files:
        if only_prefixes and not any(relative.startswith(p.rstrip("/") + "/") or relative == p for p in only_prefixes):
            continue
        files_by_origin[origin] = files_by_origin.get(origin, 0) + 1
        files_by_language[language] = files_by_language.get(language, 0) + 1
        code_lines = _collect_file(relative, language, text, origin, findings)
        if origin != "test":
            cross_file_inputs.append((relative, language, code_lines))

    # 파일을 넘는 냄새 (운영 코드만 — 테스트의 직접 호출·상수는 정상인 경우가 많다)
    bypassed, unwrapped = structure_smells.direct_call_findings(cross_file_inputs, limit)
    cross_file = {"bypassed_components": bypassed, "common_call_candidates": unwrapped,
                  "duplicate_constants": structure_smells.duplicate_constant_findings(cross_file_inputs)}

    report = scan_report.build_report(findings, cross_file, limit, categories)
    return {
        "root": str(root),
        "files_scanned": sum(files_by_origin.values()),
        "files_by_origin": files_by_origin,
        "files_by_language": files_by_language,
        "not_analyzed_languages": inventory.not_analyzed_languages,
        "excluded": inventory.excluded_summary(),
        "owned_tooling": inventory.owned_tooling,
        **report,
        "summary_text": scan_report.summary_text(files_by_origin, report["counts"], report["test_counts"],
                                                 inventory.excluded_summary(), inventory.not_analyzed_languages),
    }


def record_metrics(root: Path, summary: dict, rule_counts: dict) -> Path:
    """docs/architecture/metrics.jsonl 에 한 줄 추가 (추이 비교용)"""
    path = root / "docs" / "architecture" / "metrics.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"date": date.today().isoformat(), "summary": summary, "rules": rule_counts}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    return path


def _collect_file(relative: str, language: str, text: str, origin: str, findings: dict) -> list:
    """한 파일의 냄새를 findings 에 담고, 파일을 넘는 검사용 코드 줄 [(번호, 줄)]을 돌려준다"""
    tag = {} if origin == "production" else {"origin": origin}  # test 만 test_counts 로 (scan_report)
    classified = classify_lines(text, language)
    lines = text.splitlines()
    comment_lines = sum(1 for _, kind, _ in classified if kind == "comment")
    code_line_count = sum(1 for _, kind, _ in classified if kind == "code")

    # 크기·주석 비율·긴 함수
    if len(classified) > REVIEW_SPLIT_LINES:
        findings["long_files"].append({"path": relative, "lines": len(classified), **tag})
    if code_line_count and comment_lines > code_line_count:
        extra = {"is_declaration_only": True} if DECLARATION_ONLY_PATTERN.search(text) or relative.endswith(".d.ts") else {}
        findings["comment_heavy_files"].append(
            {"path": relative, "comment_lines": comment_lines, "code_lines": code_line_count, **extra, **tag})
    for function in structure_smells.long_functions(text, language):
        findings["long_functions"].append({"path": relative, **function, **tag})

    # 주석 블록: 주석 처리된 코드는 따로, 라이선스는 제외, 나머지는 성격(kind)을 붙여 긴 블록으로
    for start, length, contents in comment_blocks(classified):
        block_kind = code_smells.comment_block_kind(start, contents)
        if block_kind == "commented_code":
            findings["commented_out_code"].append({"path": relative, "line": start, "length": length, **tag})
        elif block_kind != "license" and length >= code_smells.LONG_COMMENT_BLOCK_LINES:
            findings["long_comment_blocks"].append({"path": relative, "line": start, "length": length,
                                                    "kind": block_kind, **tag})

    # 줄 단위: 주석 문구, 이름, 토큰, URL
    contract = naming_smells.contract_reason(relative, text)
    embedded_numbers = code_smells.embedded_text_lines(text, language)
    code_lines = []
    for number, kind, content in classified:
        if content:
            for phrase_kind in code_smells.comment_phrase_findings(content):
                findings[f"{phrase_kind}_comments"].append({"path": relative, "line": number, "text": content[:160], **tag})
        if kind != "code":
            continue
        line = lines[number - 1]
        code_lines.append((number, line))
        if number in embedded_numbers:
            continue
        _collect_names(relative, language, line, number, lines, contract, findings, tag)
        for token_kind in code_smells.hardcoded_tokens_in_line(line, language, relative):
            findings["hardcoded_tokens"].append({"path": relative, "line": number, "kind": token_kind, **tag})
        for url in code_smells.hardcoded_urls_in_line(line):
            findings["hardcoded_urls"].append({"path": relative, "line": number, "url": url, **tag})

    # 파일 단위: 타입명, catch 처리, 린트 끄기, 운영에 섞인 테스트 코드
    mismatched_type = naming_smells.file_type_name_mismatch(relative, language, text)
    if mismatched_type:
        findings["file_type_mismatch"].append({"path": relative, "first_type": mismatched_type, **tag})
    for catch in code_smells.swallowed_catch_findings(text, language):
        findings["swallowed_catch"].append({"path": relative, **catch, **tag})
    for catch in code_smells.unhandled_catch_findings(text, language):
        findings["unhandled_catch"].append({"path": relative, **catch, **tag})
    marker = code_smells.lint_disabled_marker(text)
    if marker:
        findings["lint_disabled_files"].append({"path": relative, "marker": marker, **tag})
    if origin != "test" and _is_test_code_in_production(relative):
        findings["test_code_in_production"].append({"path": relative})
    return code_lines


def _collect_names(relative, language, line, number, lines, contract, findings, tag):
    """boolean·약어·뜻 없는 이름 (override 자리는 빼고, 계약 파일은 contract 태그)"""
    is_override = naming_smells.is_override_context("\n".join(lines[max(0, number - 3):number - 1]) + line)
    contract_tag = {"contract": contract} if contract else {}
    if not is_override:
        for name in naming_smells.boolean_names_in_line(line, language):
            findings["boolean_names"].append({"path": relative, "line": number, "name": name, **contract_tag, **tag})
        for name in naming_smells.boolean_function_names_in_line(line, language):
            findings["boolean_functions"].append({"path": relative, "line": number, "name": name, **tag})
    for finding_kind, name, word in naming_smells.naming_findings_in_line(line, language):
        target = "abbreviations" if finding_kind == "abbreviation" else "meaningless_names"
        findings[target].append({"path": relative, "line": number, "name": name, "word": word, **tag})


def _is_test_code_in_production(relative: str) -> bool:
    directories = relative.split("/")[:-1]
    return bool(TEST_CODE_DIRECTORY_NAMES & set(directories)) or bool(TEST_CODE_FILE_PATTERN.match(relative.rsplit("/", 1)[-1]))
