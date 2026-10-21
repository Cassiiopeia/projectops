"""보드 HTML 조립: 주제별 섹션, 출처·상태 표시, 그림 한 번만 싣기"""
from __future__ import annotations

import base64
import html
import mimetypes
import unicodedata
from pathlib import Path

from pro_design_brief.settings import _TEMPLATE


# =========================================================================
# board — 데이터 JSON → HTML (+ 주제별 PNG)
# =========================================================================
#
# PIL 로 좌표를 계산해 합치던 방식은 글자 배치를 여러 번 고쳐야 했다(확대 영역 두 번 수정).
# HTML 로 짜고 브라우저로 찍으면 글자 흐름은 브라우저가 맡는다.

TOPICS = [
    ("summary", "Summary"), ("current", "Current implementation"), ("states", "States"),
    ("alternatives", "Alternatives"), ("copy", "Copy"), ("ui", "UI elements"), ("impact", "Dev impact"),
]

# 캡처가 어디서 왔는지. **렌더는 상태를 연출하는 수단이지 사실의 근거가 아니다** (#636) —
# 렌더만 보고 쓴 주장 7건이 실기기와 달랐다(모달 가림막 · 오프라인 경로 · 자동 재시도 · 기기 폭 · 픽스처 값).
SOURCE_TAG = {
    "render": ("Render · fake data", "src-render"),
    "device": ("Real device", "src-device"),
    "server": ("Production server", "src-server"),
    "design": ("Design", "src-design"),
    "ascii": ("ASCII", "src-ascii"),
}
# 사실 주장의 근거로 인정하는 것. render 는 빠진다.
FACT_BASIS = {"device": "Real device", "server": "Production API/config", "code": "Code", "design": "Design"}

# 상태가 지금 흐름에서 나오는가. 나오지 않는 상태를 요청하면 디자이너가 헛일을 한다 (#636 실측).
REACHABLE_TAG = {
    "yes": ("Reachable now", "done"),
    "old_data": ("Old data only", "none"),
    "unknown": ("Not verified", "temp"),
}

_STATUS_TAG = {"done": ("Implemented", "done"), "temp": ("Temporary screen", "temp"),
               "none": ("Not implemented", "none"), "missing": ("Not implemented", "none")}


def _e(v) -> str:
    return html.escape("" if v is None else str(v))


# 같은 캡처를 여러 칸(현재 구현 · 상태 · 대안)에서 쓴다. 칸마다 base64 를 박으면
# 한 장이 서너 번 실려 HTML 이 16MB 가 됐다 (실측). 그림은 한 번만 싣고 id 로 잇는다.
_IMAGES: dict[str, tuple[str, str]] = {}   # 경로 → (id, data URI)
EMBED_MAX_SIDE = 1440   # 보드에서 가장 크게 보이는 폭(360px)의 2배 배율 + 여유


def _data_uri(p: Path) -> str:
    """표시에 충분한 크기로 줄여 싣는다. Pillow 가 없으면 원본 그대로 — 무거울 뿐 깨지지 않는다."""
    raw, mime = p.read_bytes(), mimetypes.guess_type(p.name)[0] or "image/png"
    try:
        from io import BytesIO

        from PIL import Image
        with Image.open(p) as im:
            if max(im.size) > EMBED_MAX_SIDE:
                im.thumbnail((EMBED_MAX_SIDE, EMBED_MAX_SIDE), Image.LANCZOS)
                buf = BytesIO()
                im.save(buf, "PNG", optimize=True)
                raw, mime = buf.getvalue(), "image/png"
    except Exception:
        pass  # Pillow 없음·이미지 손상 — 줄이지 않고 원본을 싣는다
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _img(path_str: str, base: Path, cls: str = "") -> str:
    p = Path(path_str)
    if not p.is_absolute():
        p = base / p
    if not p.is_file():
        return f'<div class="muted">Image not found: {_e(path_str)}</div>'
    key = str(p.resolve())
    if key not in _IMAGES:
        _IMAGES[key] = (f"img{len(_IMAGES) + 1}", _data_uri(p))
    img_id = _IMAGES[key][0]
    return f'<img class="{cls}" data-img="{img_id}" alt="{_e(p.name)}">'


def _image_script() -> str:
    table = ",".join(f'"{i}":"{uri}"' for i, uri in _IMAGES.values())
    return ("<script>const IMGS={" + table + "};"
            "document.querySelectorAll('img[data-img]').forEach(e=>{e.src=IMGS[e.dataset.img];});</script>")


def _ascii_html(text: str) -> str:
    """전각 글자를 두 칸 폭 칸에 넣는다. text_width 와 같은 규칙이라야 줄 끝이 맞는다."""
    out = []
    for c in str(text):
        esc = html.escape(c)
        out.append(f'<span class="w">{esc}</span>' if unicodedata.east_asian_width(c) in "WF" else esc)
    return "".join(out)


def _source_tag(source) -> str:
    if not source:
        return ""
    text, cls = SOURCE_TAG.get(source, (str(source), "src-render"))
    return f'<span class="tag {cls}">{_e(text)}</span> '


def _figure(item: dict, base: Path) -> str:
    label = _source_tag(item.get("source")) + _e(item.get("label") or item.get("name"))
    zoom = " zoom" if item.get("zoom") else ""
    if item.get("image"):
        body = _img(item["image"], base)
    elif item.get("ascii"):
        body = f'<pre class="ascii">{_ascii_html(item["ascii"])}</pre>'
    else:
        body = '<div class="muted">No capture</div>'
    return f'<figure class="{zoom.strip()}">{body}<figcaption>{label}</figcaption></figure>'


def _ul(items) -> str:
    return "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in items or []) + "</ul>" if items else ""


def _section(topic: str, title: str, inner: str) -> str:
    return f'<section class="topic" id="{topic}"><h2>{_e(title)}</h2>{inner}</section>'


def build_sections(data: dict, base: Path) -> list[tuple[str, str, str]]:
    """(주제 id, 제목, HTML). 데이터에 없는 주제는 만들지 않는다 — 빈 칸을 보여 주지 않는다."""
    out = []
    s = data.get("summary") or {}
    inner = ('<div class="banner">This is material to think with, not the answer. Feel free to change any alternative, copy or element.'
             + (f' {_e(s.get("note"))}' if s.get("note") else "") + "</div>")
    inner += "<dl class=\"kv\">"
    for k, label in (("what", "What"), ("why", "Why"), ("status", "Current state"), ("recommend", "Dev recommendation")):
        if s.get(k):
            inner += f"<dt>{label}</dt><dd>{_e(s[k])}</dd>"
    inner += "</dl>"
    if s.get("must_keep"):
        inner += "<h3>Must keep</h3><table><tr><th>What</th><th>Source</th></tr>" + "".join(
            f"<tr><td>{_e(m.get('rule') if isinstance(m, dict) else m)}</td>"
            f"<td class='muted'>{_e(m.get('source') if isinstance(m, dict) else '')}</td></tr>"
            for m in s["must_keep"]) + "</table>"
    if data.get("facts"):
        rows = []
        for f in data["facts"]:
            basis = f.get("basis")
            label = FACT_BASIS.get(basis) or ("Render: not evidence" if basis == "render" else "No evidence")
            cls = "done" if basis in FACT_BASIS else "none"
            rows.append(f"<tr><td>{_e(f.get('claim'))}</td><td><span class='tag {cls}'>{_e(label)}</span></td>"
                        f"<td class='muted'>{_e(f.get('ref'))}</td></tr>")
        inner += ("<h3>Facts about the current app and their evidence</h3><table><tr><th>Fact</th><th>Evidence</th><th>Where</th></tr>"
                  + "".join(rows) + "</table>")
    out.append(("summary", "Summary", inner))

    if data.get("current"):
        inner = '<div class="grid">' + "".join(_figure(c, base) for c in data["current"]) + "</div>"
        out.append(("current", "Current implementation", inner))

    if data.get("states"):
        rows = []
        for st in data["states"]:
            label, cls = _STATUS_TAG.get(st.get("status"), (st.get("status") or "?", "temp"))
            design = st.get("design")
            design_cell = ("" if design is None else
                           "<td>" + ("✅ Drawn" if design is True else "❌ None" if design is False
                                     else _e(design)) + "</td>")
            shot = _figure({"image": st.get("image"), "ascii": st.get("ascii"),
                            "source": st.get("source") or ("ascii" if st.get("ascii") and not st.get("image") else None),
                            "label": "Render failed: ASCII" if st.get("render_failed") else ""}, base) \
                if (st.get("image") or st.get("ascii")) else '<span class="muted">—</span>'
            copy = ('<span class="tag none">Copy needed</span>' if st.get("copy_needed") else _e(st.get("copy")))
            reach = REACHABLE_TAG.get(st.get("reachable"))
            reach_html = (f"<br><span class='tag {reach[1]}'>{reach[0]}</span>" if reach else "")
            rows.append(f"<tr><td>{_e(st.get('axis'))}</td><td><b>{_e(st.get('name'))}</b>{reach_html}</td>"
                        f"<td><span class='tag {cls}'>{label}</span></td>{design_cell}"
                        f"<td>{copy}</td><td>{shot}</td></tr>")
        has_design = any(st.get("design") is not None for st in data["states"])
        head = ("<tr><th>Axis</th><th>State</th><th>Implementation</th>" + ("<th>Design</th>" if has_design else "")
                + "<th>Copy</th><th>Screen</th></tr>")
        out.append(("states", "States", f"<table>{head}{''.join(rows)}</table>"))

    if data.get("alternatives"):
        cards = []
        for a in data["alternatives"]:
            rec = ' <span class="tag rec">Dev recommendation</span>' if a.get("recommended") else ""
            src = a.get("source")
            pics = "".join(_figure({"image": im, "label": "", "source": src}, base) for im in a.get("images") or [])
            if a.get("image"):
                pics = _figure({"image": a["image"], "label": "", "source": src}, base) + pics
            if a.get("zoom"):
                pics += _figure({"image": a["zoom"], "label": "Zoom", "zoom": True}, base)
            if a.get("ascii"):
                # 렌더할 코드가 아직 없는 안(새 화면 등) — 무엇이 어디 있는지만 전한다
                pics += _figure({"ascii": a["ascii"], "label": "ASCII: cannot show fonts, spacing or colors"}, base)
            cards.append(f'<div class="alt"><h3>Option {_e(a.get("id"))} · {_e(a.get("name"))}{rec}</h3>'
                         f'<div class="grid">{pics}</div>'
                         f'<b>Pros</b>{_ul(a.get("pros"))}<b>Cons</b>{_ul(a.get("cons"))}'
                         f'<b>Dev impact</b><p>{_e(a.get("dev_impact") or "None")}</p></div>')
        out.append(("alternatives", "Alternatives", '<div class="grid">' + "".join(cards) + "</div>"))

    if data.get("copy"):
        rows = []
        for c in data["copy"]:
            if c.get("legal"):
                cand = '<span class="tag legal">Legal copy: do not change</span>'
            elif c.get("needed"):
                cand = '<span class="tag none">Copy needed</span>'
            else:
                cand = _ul(c.get("candidates"))
            rows.append(f"<tr><td>{_e(c.get('where'))}</td><td>{_e(c.get('current'))}</td>"
                        f"<td>{cand}</td><td class='muted'>{_e(c.get('reason'))}</td></tr>")
        out.append(("copy", "Copy", "<table><tr><th>Where</th><th>Current</th><th>Candidates</th><th>Reason</th></tr>"
                    + "".join(rows) + "</table>"))

    if data.get("ui"):
        rows = "".join(
            f"<tr><td>{_e(u.get('shape'))}</td><td>{_ul(u.get('candidates'))}</td>"
            f"<td>{_ul(u.get('existing'))}</td><td>{_ul(u.get('new'))}</td></tr>" for u in data["ui"])
        out.append(("ui", "UI elements", "<table><tr><th>Data shape</th><th>Candidates</th>"
                    "<th>Components already in the repo</th><th>New components</th></tr>" + rows + "</table>"))

    if data.get("impact"):
        rows = "".join(f"<tr><td>{_e(i.get('choice'))}</td><td>{_e(i.get('work'))}</td></tr>"
                       for i in data["impact"])
        out.append(("impact", "Dev impact", "<table><tr><th>If chosen</th><th>Extra development needed</th></tr>"
                    + rows + "</table>"))
    return out


def render_html(data: dict, base: Path) -> tuple[str, list[str]]:
    _IMAGES.clear()
    sections = build_sections(data, base)
    tpl = _TEMPLATE.read_text(encoding="utf-8")
    nav = "".join(f'<button type="button" data-show="{t}" aria-pressed="false">{_e(title)}</button>'
                  for t, title, _ in sections)
    body = "\n".join(_section(t, title, inner) for t, title, inner in sections)
    # 자리표시는 **한 번만** 바꾼다 — 템플릿 주석에 같은 글자가 있으면 보드가 두 번 실린다 (실측)
    doc = (tpl.replace("{{TITLE}}", _e(data.get("title") or "Design request"), 1)
              .replace("<!--NAV-->", nav, 1).replace("<!--SECTIONS-->", body, 1)
              .replace("</body>", _image_script() + "\n</body>", 1))
    return doc, [t for t, _, _ in sections]
