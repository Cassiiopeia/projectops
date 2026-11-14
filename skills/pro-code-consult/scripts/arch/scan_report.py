"""Organize scan results: sort categories > separate production/test counts > per-file tallies > reading order

Lists are not in path order. Most severe first; at equal weight, picked round-robin by folder
(so one folder does not fill the top of the list and hide the others). Test items go after production items.
"""
from __future__ import annotations

from itertools import zip_longest

# Reading order = risk order (behavior risk > extraction/single source > structure > comments > names/tokens)
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
# Size-sort keys (other categories alternate by folder)
SIZE_SORT_KEYS = {
    "long_files": lambda f: -f["lines"],
    "long_functions": lambda f: -f["lines"],
    "comment_heavy_files": lambda f: (f.get("is_declaration_only", False), -(f["comment_lines"] - f["code_lines"])),
    "long_comment_blocks": lambda f: (f["kind"] != "prose", -f["length"]),
    "commented_out_code": lambda f: -f["length"],
    # Lower priority last: failure recorded in result, reported to screen, translation after business exceptions pass > log only > narrow catch
    "unhandled_catch": lambda f: (f.get("records_failure", False) or f.get("sets_error_state", False)
                                  or f.get("has_passthrough_before", False),
                                  f["has_log"] and f["kind"] == "no_rethrow", not f["is_catch_all"], -f["body_lines"]),
}
# File line count that must be split (conventions §3.3)
MUST_SPLIT_LINES = 500
HOTSPOT_COUNT = 15
# Categories left out of per-file tallies (file-level facts would be double-counted)
HOTSPOT_SKIPPED = {"long_files", "comment_heavy_files", "file_type_mismatch", "lint_disabled_files", "test_code_in_production"}


def build_report(findings: dict, cross_file: dict, limit: int, categories: list | None) -> dict:
    counts, test_counts, ordered = {}, {}, {}
    for category, items in findings.items():
        # tooling/generated/vendored included via --all count as production (only test is separate)
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
    """Alternate by folder (first 3 path levels) — larger folders first"""
    by_area = {}
    for item in items:
        by_area.setdefault("/".join(item["path"].split("/")[:3]), []).append(item)
    queues = sorted(by_area.values(), key=len, reverse=True)
    return [item for row in zip_longest(*queues) for item in row if item is not None]


def _hotspots(findings: dict) -> list:
    """Production files with the most candidates (starting point for grouping causes: many categories in one file means that file is the cause)"""
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
