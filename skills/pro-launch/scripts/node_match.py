"""Picking screen elements — matcher shared by Android · iOS (#927).

app tap · app run use only this module to pick nodes by --text/--desc/--id.
Order: exact > equal after normalizing (doubled labels · invisible marks · whitespace, per line) > contains.
Within a stage the requested field comes first, then the other text field (text <-> desc).
"""
from __future__ import annotations

import difflib
import re
import shlex

# Text fields stand in for each other (Flutter Semantics labels land in desc; on iOS accessibilityText also lands in text)
TEXT_LIKE_FIELDS = ("text", "desc")
# Invisible direction and width marks (LRM·RLM·ZWSP·ZWNJ·ZWJ·WJ·BOM·direction overrides)
INVISIBLE_MARKS = re.compile("[\u200b-\u200f\u2060\ufeff\u202a-\u202e]")
MATCH_KINDS = ("exact", "normalized", "partial")
# Minimum similarity offered as did_you_mean (0-1)
SUGGESTION_MINIMUM_RATIO = 0.5


def label_lines(raw: str) -> list[str]:
    """Normalized lines (invisible marks removed · single spaces) — matches per line the desc Flutter builds by joining several Semantics with newlines."""
    lines = (" ".join(INVISIBLE_MARKS.sub("", line).split()) for line in (raw or "").splitlines())
    return [line for line in lines if line]


def normalize_label(raw: str) -> str:
    """'X\\nX' > 'X'. Different lines are joined with a space."""
    lines = label_lines(raw)
    if lines and all(line == lines[0] for line in lines):
        return lines[0]
    return " ".join(lines)


def _is_match(node_value: str, value: str, field: str, kind: str) -> bool:
    if kind == "exact":
        return node_value == value or (field == "id" and node_value.endswith(":id/" + value))
    wanted = normalize_label(value)
    if not wanted or not node_value:
        return False
    if kind == "normalized":
        return normalize_label(node_value) == wanted or wanted in label_lines(node_value)
    return wanted in normalize_label(node_value)


def _search_fields(field: str) -> tuple[str, ...]:
    """Requested field first, and for text fields the other text field too. id checks id only."""
    if field not in TEXT_LIKE_FIELDS:
        return (field,)
    return (field, *(other for other in TEXT_LIKE_FIELDS if other != field))


def find_nodes(nodes: list[dict], field: str, value: str) -> tuple[list[dict], str | None, str | None]:
    """> (matched nodes, matched field, matched stage). If not found ([], None, None)."""
    for kind in MATCH_KINDS:
        for search_field in _search_fields(field):
            found = [n for n in nodes if _is_match(n.get(search_field) or "", value, search_field, kind)]
            if found:
                return found, search_field, kind
    return [], None, None


def match_nodes(nodes: list[dict], field: str, value: str) -> list[dict]:
    """Matched node list only (for app run step targets and visibility checks)."""
    return find_nodes(nodes, field, value)[0]


def candidate_values(nodes: list[dict], field: str, limit: int = 25) -> list[str]:
    """Values actually on screen — for text fields both text and desc (doubled labels normalized)."""
    fields = TEXT_LIKE_FIELDS if field in TEXT_LIKE_FIELDS else (field,)
    values = (normalize_label(n.get(f) or "") if f in TEXT_LIKE_FIELDS else (n.get(f) or "")
              for n in nodes for f in fields)
    return list(dict.fromkeys(v for v in values if v))[:limit]


def did_you_mean(nodes: list[dict], value: str) -> str | None:
    """Closest value across all fields > in the form '--desc Home'. None if nothing is similar."""
    wanted = normalize_label(value)
    best_ratio, best = 0.0, None
    for node in nodes:
        for field in ("text", "desc", "id"):
            candidate = normalize_label(node.get(field) or "")
            if not candidate or not wanted:
                continue
            ratio = difflib.SequenceMatcher(None, wanted, candidate).ratio()
            # If one contains the other, short labels (Home <-> Home tab) are candidates too
            if wanted in candidate or candidate in wanted:
                ratio = max(ratio, SUGGESTION_MINIMUM_RATIO + 0.1)
            if ratio > best_ratio:
                best_ratio, best = ratio, (field, candidate)
    if best is None or best_ratio < SUGGESTION_MINIMUM_RATIO:
        return None
    return f"--{best[0]} {shlex.quote(best[1])}"
