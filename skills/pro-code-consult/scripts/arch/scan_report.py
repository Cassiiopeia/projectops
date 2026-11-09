"""scan 결과 정리: 범주 정렬 > 운영/테스트 분리 수치 > 파일별 집계 > 읽는 순서

목록은 경로 순이 아니다. 심한 것 먼저, 같은 무게면 폴더마다 번갈아 뽑는다
(한 폴더가 상위 목록을 다 채워 다른 폴더가 안 보이는 일 방지). 테스트 항목은 운영 항목 뒤에 둔다.
"""
from __future__ import annotations

from itertools import zip_longest

# 읽는 순서 = 위험도 순 (동작 위험 > 공통화·단일 원본 > 구조 > 주석 > 이름·토큰)
REVIEW_ORDER = (
    ("behavior risk", ("unhandled_catch", "test_code_in_production", "swallowed_catch", "hardcoded_urls", "lint_disabled_files")),
    ("common code and single source", ("bypassed_components", "common_call_candidates", "duplicate_constants")),
    ("structure", ("long_files", "long_functions", "file_type_mismatch")),
    ("comments", ("history_comments", "commented_out_code", "long_comment_blocks", "comment_heavy_files",
             "banner_comments", "prose_ending_comments")),
    ("names and tokens", ("boolean_functions", "boolean_names", "abbreviations", "meaningless_names", "hardcoded_tokens")),
)
CROSS_FILE_CATEGORIES = ("bypassed_components", "common_call_candidates", "duplicate_constants")
PER_FILE_CATEGORIES = tuple(c for _, group in REVIEW_ORDER for c in group if c not in CROSS_FILE_CATEGORIES)
# 크기 순 정렬 기준 (나머지 범주는 폴더 번갈아)
SIZE_SORT_KEYS = {
    "long_files": lambda f: -f["lines"],
    "long_functions": lambda f: -f["lines"],
    "comment_heavy_files": lambda f: (f.get("is_declaration_only", False), -(f["comment_lines"] - f["code_lines"])),
    "long_comment_blocks": lambda f: (f["kind"] != "prose", -f["length"]),
    "commented_out_code": lambda f: -f["length"],
    # 낮은 것 뒤로: 실패를 결과에 담음·화면에 알림·업무 예외 통과 후 번역 > 로그만 > 좁은 catch
    "unhandled_catch": lambda f: (f.get("records_failure", False) or f.get("sets_error_state", False)
                                  or f.get("has_passthrough_before", False),
                                  f["has_log"] and f["kind"] == "no_rethrow", not f["is_catch_all"], -f["body_lines"]),
}
# 반드시 분리할 파일 줄 수 (conventions §3.3)
MUST_SPLIT_LINES = 500
HOTSPOT_COUNT = 15
# 파일별 집계에서 뺄 범주 (파일 단위 사실이라 중복 집계가 됨)
HOTSPOT_SKIPPED = {"long_files", "comment_heavy_files", "file_type_mismatch", "lint_disabled_files", "test_code_in_production"}


def build_report(findings: dict, cross_file: dict, limit: int, categories: list | None) -> dict:
    counts, test_counts, ordered = {}, {}, {}
    for category, items in findings.items():
        # --all 로 넣은 tooling·generated·vendored 는 운영 쪽 수치 (test 만 따로)
        production = [f for f in items if not _is_test_item(f)]
        others = [f for f in items if _is_test_item(f)]
        counts[category] = len(production)
        if others:
            test_counts[category] = len(others)
        ordered[category] = _ordered(category, production) + _ordered(category, others)
    for category, items in cross_file.items():
        counts[category] = len(items)
        ordered[category] = items
    counts["must_split_files"] = sum(1 for f in findings["long_files"] if not _is_test_item(f) and f["lines"] > MUST_SPLIT_LINES)

    selected = categories or list(ordered)
    limited = {c: ordered[c][:limit] for c in selected if c in ordered}
    truncated = {c: len(ordered[c]) for c in selected if c in ordered and len(ordered[c]) > limit}
    return {
        "counts": counts,
        "test_counts": test_counts,
        "findings": limited,
        "truncated": truncated,
        "hotspots": _hotspots(findings),
        "review_order": [{"group": group, "categories": [c for c in members if counts.get(c)]}
                         for group, members in REVIEW_ORDER],
    }


def summary_text(files_by_origin: dict, counts: dict, test_counts: dict, excluded: dict,
                 not_analyzed_languages: dict | None = None) -> str:
    excluded_text = ", ".join(f"{origin} {entry['count']}" for origin, entry in excluded.items()) or "none"
    groups = []
    for group, members in REVIEW_ORDER:
        present = [f"{c} {counts[c]}" for c in members if counts.get(c)]
        if present:
            groups.append(f"[{group}] " + ", ".join(present))
    parts = [f"{files_by_origin.get('production', 0)} production, {files_by_origin.get('test', 0)} test files (excluded: {excluded_text})"]
    parts += [" | ".join(groups)] if groups else []
    if test_counts:
        parts.append(f"{sum(test_counts.values())} test-side candidates are in test_counts")
    if not_analyzed_languages:
        parts.append("languages the CLI cannot read (sample them by hand): " + ", ".join(f"{n} {c}" for n, c in not_analyzed_languages.items()))
    return " | ".join(parts)


def _is_test_item(item: dict) -> bool:
    return item.get("origin") == "test"


def _ordered(category: str, items: list) -> list:
    if category in SIZE_SORT_KEYS:
        return sorted(items, key=SIZE_SORT_KEYS[category])
    return _round_robin_by_area(items)


def _round_robin_by_area(items: list) -> list:
    """폴더(경로 앞 3단계)마다 번갈아 — 큰 폴더 먼저"""
    by_area = {}
    for item in items:
        by_area.setdefault("/".join(item["path"].split("/")[:3]), []).append(item)
    queues = sorted(by_area.values(), key=len, reverse=True)
    return [item for row in zip_longest(*queues) for item in row if item is not None]


def _hotspots(findings: dict) -> list:
    """운영 파일별 후보 수 상위 (원인 묶기 출발점: 한 파일에 여러 범주가 몰리면 그 파일 하나가 원인)"""
    by_file = {}
    for category, items in findings.items():
        if category in HOTSPOT_SKIPPED:
            continue
        for item in items:
            if _is_test_item(item):
                continue
            entry = by_file.setdefault(item["path"], {})
            entry[category] = entry.get(category, 0) + 1
    ranked = sorted(by_file.items(), key=lambda pair: -sum(pair[1].values()))[:HOTSPOT_COUNT]
    return [{"path": path, "total": sum(categories.values()), "categories": categories} for path, categories in ranked]
