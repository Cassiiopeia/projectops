"""보드 데이터 > markdown 요청서, 게시 전 점검(preflight)"""
from __future__ import annotations

from pathlib import Path

from pro_design_brief.board_html import FACT_BASIS, REACHABLE_TAG, _STATUS_TAG


def _c(v) -> str:
    """markdown 표 칸 — `|` 가 들어오면 표가 깨진다."""
    return ("" if v is None else str(v)).replace("|", "\\|").replace("\n", " ")


def render_markdown(data: dict, png: list[str], out_dir: Path) -> str:
    """markdown 출력 — PNG 폴더와 함께 넘긴다. 표는 보드와 같은 데이터에서 나온다."""
    s = data.get("summary") or {}
    lines = [f"# {data.get('title') or 'Design request'}", "",
             "> This is material to think with, not the answer. Feel free to change any alternative, copy or element.", ""]
    for k, label in (("what", "What"), ("why", "Why"), ("status", "Current state"), ("recommend", "Dev recommendation")):
        if s.get(k):
            lines.append(f"- **{label}**: {s[k]}")
    if s.get("must_keep"):
        lines += ["", "## Must keep", "", "| What | Source |", "|---|---|"]
        for m in s["must_keep"]:
            rule = m.get("rule") if isinstance(m, dict) else m
            src = m.get("source", "") if isinstance(m, dict) else ""
            lines.append(f"| {_c(rule)} | {_c(src)} |")
    if data.get("facts"):
        lines += ["", "## Facts about the current app and their evidence", "", "| Fact | Evidence | Where |", "|---|---|---|"]
        for f in data["facts"]:
            basis = FACT_BASIS.get(f.get("basis")) or "**No evidence**"
            lines.append(f"| {_c(f.get('claim'))} | {basis} | {_c(f.get('ref'))} |")
    if data.get("states"):
        lines += ["", "## States", "", "| Axis | State | Implementation | Reachable now? | Copy |", "|---|---|---|---|---|"]
        for st in data["states"]:
            label = _STATUS_TAG.get(st.get("status"), (st.get("status") or "?", ""))[0]
            copy = "**Copy needed**" if st.get("copy_needed") else (st.get("copy") or "")
            reach = (REACHABLE_TAG.get(st.get("reachable")) or ("—", ""))[0]
            lines.append(f"| {_c(st.get('axis'))} | {_c(st.get('name'))} | {label} | {reach} | {_c(copy)} |")
    if data.get("copy"):
        lines += ["", "## Copy", "", "| Where | Current | Candidates | Reason |", "|---|---|---|---|"]
        for c in data["copy"]:
            cand = ("Legal copy: do not change" if c.get("legal") else
                    "**Copy needed**" if c.get("needed") else "<br>".join(_c(x) for x in c.get("candidates") or []))
            lines.append(f"| {_c(c.get('where'))} | {_c(c.get('current'))} | {cand} | {_c(c.get('reason'))} |")
    if png:
        lines += ["", "## Board", ""]
        for f in png:
            rel = Path(f).relative_to(out_dir) if Path(f).is_relative_to(out_dir) else Path(f)
            lines.append(f"![{Path(f).stem}]({rel.as_posix()})")
    return "\n".join(lines) + "\n"


def preflight(data: dict) -> list[str]:
    """게시 전에 걸러야 할 것. 판단은 agent 가 하지만, 빠뜨린 표시는 기계가 센다 (#636)."""
    warns: list[str] = []

    def need_source(where: str, item: dict, key: str = "image"):
        if item.get(key) and not item.get("source"):
            warns.append(f"{where}: capture source missing; set source to one of render, device, server, design")

    for i, c in enumerate(data.get("current") or []):
        need_source(f"Current implementation[{i}] {c.get('label', '')}", c)
    for st in data.get("states") or []:
        name = st.get("name", "")
        need_source(f"State '{name}'", st)
        r = st.get("reachable")
        if r is None:
            warns.append(f"State '{name}': reachable not set (does it appear in the current flow?); check the input path in the code")
        elif r == "old_data":
            warns.append(f"State '{name}': appears only with old data; reconsider whether to include it in the request")
    for a in data.get("alternatives") or []:
        if (a.get("image") or a.get("images")) and not a.get("source"):
            warns.append(f"Alternative {a.get('id', '')}: capture source missing")
    for f in data.get("facts") or []:
        basis = f.get("basis")
        if basis not in FACT_BASIS:
            why = "a render (fake data) is not evidence" if basis == "render" else "no evidence"
            warns.append(f"Fact '{f.get('claim', '')}': {why}; confirm it on a real device, the production API or in code")
        elif not f.get("ref"):
            warns.append(f"Fact '{f.get('claim', '')}': evidence location (ref) missing; give a capture file, API path or code line")
    return warns
