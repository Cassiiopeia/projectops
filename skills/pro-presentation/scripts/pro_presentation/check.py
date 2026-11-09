"""check: 덱을 기계적으로 검사 > 빠진 것 · 용어 위반 · 예상 시간 · 녹화 차수별 장 시간 · 그림으로 갈 부분
코칭 판단은 하지 않는다 (agent 몫, references/coaching.md)
"""
from __future__ import annotations

import html.parser
from pathlib import Path

from common.emit import emit

from pro_presentation.deck import load_deck

PIECE_ATTRIBUTE = "data-pp"
# 장 본체 안 최상위가 아니어도 되는 태그 (내용이 아님)
IGNORED_TOP_TAGS = {"style", "script", "br"}


class _TopLevelCollector(html.parser.HTMLParser):
    """section.slide 바로 아래 요소 중 data-pp 없는 것 > 그림으로 들어갈 부분"""

    VOID_TAGS = {"img", "br", "hr", "input", "meta", "link", "source"}

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.slide_depth: int | None = None
        self.picture_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if self.slide_depth is None and tag == "section" and "slide" in (attributes.get("class") or "").split():
            self.slide_depth = self.depth
        elif self.slide_depth is not None and self.depth == self.slide_depth + 1:
            if PIECE_ATTRIBUTE not in attributes and tag not in IGNORED_TOP_TAGS:
                selector = tag + "".join(f".{name}" for name in (attributes.get("class") or "").split())
                self.picture_parts.append(selector)
        if tag not in self.VOID_TAGS:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in self.VOID_TAGS:
            return
        self.depth -= 1
        if self.slide_depth is not None and self.depth == self.slide_depth:
            self.slide_depth = None


def find_picture_parts(slide_html: str) -> list[str]:
    collector = _TopLevelCollector()
    collector.feed(slide_html)
    return collector.picture_parts


def find_glossary_hits(deck: dict) -> list[dict]:
    """memory.md 용어 표의 '쓰지 않는다' 말이 대본(말하는 글)에 있는지 (단순 글자 일치, 카드는 설명이라 제외)"""
    hits = []
    for slide in deck["slides"]:
        for row in deck["glossary"]:
            if row["avoid"] and row["avoid"] in slide["script"]:
                hits.append({"slide": slide["number"], "id": slide["id"], "file": "script.md",
                             "avoid": row["avoid"], "instead": row["instead"], "why": row["why"]})
    return hits


def build_timing(deck: dict) -> tuple[list[dict], dict]:
    """장별 {예상, 차수별 녹화 초} + 차수별 합계(마지막 구간 끝)"""
    rows = []
    for slide in deck["slides"]:
        takes = {recording["label"]: recording["ranges"][slide["id"]][1] - recording["ranges"][slide["id"]][0]
                 for recording in deck["recordings"] if slide["id"] in recording["ranges"]}
        rows.append({"slide": slide["number"], "id": slide["id"], "title": slide["title"],
                     "estimate_seconds": slide["estimate_seconds"], "takes": takes})
    totals = {recording["label"]: max((end for _, end in recording["ranges"].values()), default=0)
              for recording in deck["recordings"]}
    return rows, totals


def cmd_check(args) -> int:
    deck_dir = Path(args.deck).expanduser().resolve()
    deck = load_deck(deck_dir)
    timing, take_totals = build_timing(deck)
    estimate = sum(slide["estimate_seconds"] for slide in deck["slides"])
    limit = deck["time_limit_seconds"]
    picture_parts = [{"slide": slide["number"], "id": slide["id"], "selector": selector}
                     for slide in deck["slides"] if slide["html"] for selector in find_picture_parts(slide["html"])]
    glossary_hits = find_glossary_hits(deck)
    unranged = [recording["label"] for recording in deck["recordings"] if not recording["ranges"]]
    summary = (f"{len(deck['slides'])} slides, estimate {estimate // 60}:{estimate % 60:02d}"
               + (f" of {limit // 60}:{limit % 60:02d}" if limit else "")
               + f", {len(glossary_hits)} glossary hits, {len(deck['problems'])} problems")
    next_steps = []
    if deck["problems"]:
        next_steps.append("fix problems")
    if glossary_hits:
        next_steps.append("rewrite glossary hits (keep the user's meaning)")
    if unranged:
        next_steps.append(f"write ranges.json for {', '.join(unranged)}")
    return emit({"summary": summary, "problems": deck["problems"], "glossary_hits": glossary_hits,
                 "estimate_seconds": estimate, "time_limit_seconds": limit,
                 "remaining_seconds": (limit - estimate) if limit else None,
                 "characters_per_second": deck["characters_per_second"], "take_totals": take_totals,
                 "timing": timing, "picture_parts": picture_parts, "recordings_without_ranges": unranged,
                 "next": "; ".join(next_steps) or None})
