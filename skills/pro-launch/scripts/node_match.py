"""화면 요소 고르기 — Android · iOS 공통 matcher (#927).

app tap · app run 이 --text/--desc/--id 값으로 노드를 고를 때 이 모듈만 쓴다.
순서: 정확히 같음 > 정규화 후 같음(겹친 라벨 · 보이지 않는 표식 · 공백, 줄 단위) > 포함.
같은 단계 안에서는 요청한 칸을 먼저, 그다음 다른 문구 칸(text <-> desc)을 본다.
"""
from __future__ import annotations

import difflib
import re
import shlex

# 문구 칸끼리는 서로 대신 본다 (Flutter Semantics 라벨은 desc 에, iOS 는 accessibilityText 가 text 에도 온다)
TEXT_LIKE_FIELDS = ("text", "desc")
# 보이지 않는 방향·폭 표식 (LRM·RLM·ZWSP·ZWNJ·ZWJ·WJ·BOM·방향 덮기)
INVISIBLE_MARKS = re.compile("[\u200b-\u200f\u2060\ufeff\u202a-\u202e]")
MATCH_KINDS = ("exact", "normalized", "partial")
# did_you_mean 으로 내밀 최소 유사도 (0~1)
SUGGESTION_MINIMUM_RATIO = 0.5


def label_lines(raw: str) -> list[str]:
    """정규화한 줄 목록 (보이지 않는 표식 제거 · 공백 하나로) — Flutter 가 Semantics 여러 개를 줄바꿈으로 합친 desc 를 줄 단위로 맞춘다."""
    lines = (" ".join(INVISIBLE_MARKS.sub("", line).split()) for line in (raw or "").splitlines())
    return [line for line in lines if line]


def normalize_label(raw: str) -> str:
    """'X\\nX' > 'X'. 줄이 서로 다르면 공백으로 잇는다."""
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
    """요청 칸 먼저, 문구 칸이면 다른 문구 칸도. id 는 id 만."""
    if field not in TEXT_LIKE_FIELDS:
        return (field,)
    return (field, *(other for other in TEXT_LIKE_FIELDS if other != field))


def find_nodes(nodes: list[dict], field: str, value: str) -> tuple[list[dict], str | None, str | None]:
    """> (맞은 노드들, 맞은 칸, 맞은 단계). 못 찾으면 ([], None, None)."""
    for kind in MATCH_KINDS:
        for search_field in _search_fields(field):
            found = [n for n in nodes if _is_match(n.get(search_field) or "", value, search_field, kind)]
            if found:
                return found, search_field, kind
    return [], None, None


def match_nodes(nodes: list[dict], field: str, value: str) -> list[dict]:
    """맞은 노드 목록만 (app run 의 단계 대상·보임 확인용)."""
    return find_nodes(nodes, field, value)[0]


def candidate_values(nodes: list[dict], field: str, limit: int = 25) -> list[str]:
    """화면에 실제로 있는 값 — 문구 칸이면 text·desc 둘 다 (겹친 라벨은 정규화해서)."""
    fields = TEXT_LIKE_FIELDS if field in TEXT_LIKE_FIELDS else (field,)
    values = (normalize_label(n.get(f) or "") if f in TEXT_LIKE_FIELDS else (n.get(f) or "")
              for n in nodes for f in fields)
    return list(dict.fromkeys(v for v in values if v))[:limit]


def did_you_mean(nodes: list[dict], value: str) -> str | None:
    """모든 칸에서 가장 비슷한 값 > '--desc 홈' 꼴. 비슷한 것이 없으면 None."""
    wanted = normalize_label(value)
    best_ratio, best = 0.0, None
    for node in nodes:
        for field in ("text", "desc", "id"):
            candidate = normalize_label(node.get(field) or "")
            if not candidate or not wanted:
                continue
            ratio = difflib.SequenceMatcher(None, wanted, candidate).ratio()
            # 한쪽이 다른 쪽을 품으면 짧은 라벨(홈 <-> 홈 탭)도 후보로
            if wanted in candidate or candidate in wanted:
                ratio = max(ratio, SUGGESTION_MINIMUM_RATIO + 0.1)
            if ratio > best_ratio:
                best_ratio, best = ratio, (field, candidate)
    if best is None or best_ratio < SUGGESTION_MINIMUM_RATIO:
        return None
    return f"--{best[0]} {shlex.quote(best[1])}"
