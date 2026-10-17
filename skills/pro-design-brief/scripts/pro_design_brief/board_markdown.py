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
    lines = [f"# {data.get('title') or '디자인 요청서'}", "",
             "> 정답이 아니라 생각할 재료입니다. 대안·문구·요소 전부 바꿔도 됩니다.", ""]
    for k, label in (("what", "무엇을"), ("why", "왜"), ("status", "지금 상태"), ("recommend", "개발 쪽 추천")):
        if s.get(k):
            lines.append(f"- **{label}**: {s[k]}")
    if s.get("must_keep"):
        lines += ["", "## 꼭 지킬 것", "", "| 무엇 | 출처 |", "|---|---|"]
        for m in s["must_keep"]:
            rule = m.get("rule") if isinstance(m, dict) else m
            src = m.get("source", "") if isinstance(m, dict) else ""
            lines.append(f"| {_c(rule)} | {_c(src)} |")
    if data.get("facts"):
        lines += ["", "## 지금 앱에 대한 사실과 근거", "", "| 사실 | 근거 | 어디서 |", "|---|---|---|"]
        for f in data["facts"]:
            basis = FACT_BASIS.get(f.get("basis")) or "**근거 없음**"
            lines.append(f"| {_c(f.get('claim'))} | {basis} | {_c(f.get('ref'))} |")
    if data.get("states"):
        lines += ["", "## 상태", "", "| 축 | 상태 | 구현 | 지금 나오나 | 문구 |", "|---|---|---|---|---|"]
        for st in data["states"]:
            label = _STATUS_TAG.get(st.get("status"), (st.get("status") or "?", ""))[0]
            copy = "**문구 필요**" if st.get("copy_needed") else (st.get("copy") or "")
            reach = (REACHABLE_TAG.get(st.get("reachable")) or ("—", ""))[0]
            lines.append(f"| {_c(st.get('axis'))} | {_c(st.get('name'))} | {label} | {reach} | {_c(copy)} |")
    if data.get("copy"):
        lines += ["", "## 문구", "", "| 자리 | 현재 | 후보 | 이유 |", "|---|---|---|---|"]
        for c in data["copy"]:
            cand = ("법적 문구 — 바꾸면 안 됨" if c.get("legal") else
                    "**문구 필요**" if c.get("needed") else "<br>".join(_c(x) for x in c.get("candidates") or []))
            lines.append(f"| {_c(c.get('where'))} | {_c(c.get('current'))} | {cand} | {_c(c.get('reason'))} |")
    if png:
        lines += ["", "## 보드", ""]
        for f in png:
            rel = Path(f).relative_to(out_dir) if Path(f).is_relative_to(out_dir) else Path(f)
            lines.append(f"![{Path(f).stem}]({rel.as_posix()})")
    return "\n".join(lines) + "\n"


def preflight(data: dict) -> list[str]:
    """게시 전에 걸러야 할 것. 판단은 agent 가 하지만, 빠뜨린 표시는 기계가 센다 (#636)."""
    warns: list[str] = []

    def need_source(where: str, item: dict, key: str = "image"):
        if item.get(key) and not item.get("source"):
            warns.append(f"{where}: 캡처 출처가 없다 — source 를 render · device · server · design 중 하나로")

    for i, c in enumerate(data.get("current") or []):
        need_source(f"현재 구현[{i}] {c.get('label', '')}", c)
    for st in data.get("states") or []:
        name = st.get("name", "")
        need_source(f"상태 '{name}'", st)
        r = st.get("reachable")
        if r is None:
            warns.append(f"상태 '{name}': 지금 흐름에서 나오는지(reachable) 적지 않았다 — 입력 경로를 코드로 확인한다")
        elif r == "old_data":
            warns.append(f"상태 '{name}': 예전 데이터에만 나온다 — 요청에 넣을지 다시 본다")
    for a in data.get("alternatives") or []:
        if (a.get("image") or a.get("images")) and not a.get("source"):
            warns.append(f"대안 {a.get('id', '')}: 캡처 출처가 없다")
    for f in data.get("facts") or []:
        basis = f.get("basis")
        if basis not in FACT_BASIS:
            why = "렌더(가짜 데이터)는 근거가 아니다" if basis == "render" else "근거가 없다"
            warns.append(f"사실 '{f.get('claim', '')}': {why} — 실기기 · 운영 API · 코드로 확인한다")
        elif not f.get("ref"):
            warns.append(f"사실 '{f.get('claim', '')}': 근거 위치(ref)가 없다 — 캡처 파일 · API 경로 · 코드 줄")
    return warns
