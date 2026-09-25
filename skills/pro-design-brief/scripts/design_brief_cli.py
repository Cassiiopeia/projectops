#!/usr/bin/env python3
"""design_brief_cli — pro-design-brief 전용 CLI (projectops 3-layer 표준, Layer 2, #634).

디자이너에게 넘길 요청서(보드)를 조립한다. **판단은 agent, 스크립트는 실행과 기록만** 한다 —
상태 목록·대안·문구 후보를 고르는 것은 agent 이고, 여기서는 설정을 풀고 보드를 조립하고
기계적으로 검사할 수 있는 것만 검사한다.

서브커맨드:
    config show|set   design_brief 설정 해석(일치 항목 · 출처) / 저장
    get-output-path   이번 요청서의 산출물 자리
    board             데이터 JSON → 보드 HTML (+ --png 면 주제별 PNG)
    copy-lint         문구 후보의 기계적 검사 (em dash · 가운뎃점 · 금지어 · 번역투)
    ascii             박스 문자 와이어 (한글 폭 보정)

출력: MCP-style JSON (ok/code/summary/next 4필드 보장).
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402
from common.state import venv_site_packages  # noqa: E402

SKILL_ID = "design-brief"
_TEMPLATE = _HERE.parents[1] / "assets" / "board.html"
DESTINATIONS = ("issue", "html", "markdown")
# 한 장 폭 상한. GitHub 은 이보다 넓은 그림을 줄여 보여 글자가 안 읽힌다.
MAX_PNG_WIDTH = 3400


# =========================================================================
# config — design_brief 섹션 (github 아래에 두지 않는다: GitHub 을 안 쓰는 레포도 있다)
# =========================================================================

def _config_path() -> Path:
    return Path.home() / ".projectops" / "config" / "config.json"


def _load_config() -> dict:
    f = _config_path()
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _repo_identity(root: Path) -> dict:
    """{slug: owner/repo 또는 None, path: 레포 절대경로, github: bool}."""
    top = _git(root, "rev-parse", "--show-toplevel") or str(root)
    url = _git(root, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url) if url else None
    return {"slug": f"{m.group(1)}/{m.group(2)}" if m else None,
            "path": str(Path(top).resolve()), "github": bool(m)}


def resolve_config(root: Path, config: dict | None = None) -> dict:
    """우선순위: projects[] 일치 항목 → 섹션 기본값 → 없음(첫 실행 판정)."""
    config = _load_config() if config is None else config
    section = config.get("design_brief") if isinstance(config.get("design_brief"), dict) else {}
    ident = _repo_identity(root)
    match = None
    for p in section.get("projects") or []:
        if not isinstance(p, dict) or not p.get("match"):
            continue
        key = str(p["match"])
        if (ident["slug"] and key.lower() == ident["slug"].lower()) or \
           (key.startswith("/") and Path(key).resolve() == Path(ident["path"])):
            match = p
            break

    resolved, source = {}, {}
    for k in ("destination", "designer", "auto_approve"):
        if match and k in match:
            resolved[k], source[k] = match[k], "project"
        elif k in section:
            resolved[k], source[k] = section[k], "default"
        else:
            resolved[k], source[k] = None, "none"
    if resolved["auto_approve"] is None:
        resolved["auto_approve"] = False   # 안전한 기본값 — 게시 전에 확인받는다

    # 판정 거리 — 정하지 않은 것에 대해 제안만 한다. 저장은 사람이 고른 뒤에.
    suggest = {}
    if resolved["destination"] is None:
        repos = (config.get("github") or {}).get("repos") or []
        known = ident["slug"] and any(
            f"{r.get('owner')}/{r.get('repo')}".lower() == ident["slug"].lower()
            for r in repos if isinstance(r, dict))
        suggest["destination"] = "issue" if (ident["github"] and known) else \
                                 ("issue" if ident["github"] else "html")
        suggest["destination_why"] = ("GitHub 레포이고 등록돼 있다" if known else
                                      "GitHub 레포다 (등록은 안 돼 있다)" if ident["github"] else
                                      "GitHub 레포가 아니다")
    if resolved["designer"] is None:
        suggest["designer_candidates"] = _designer_from_templates(Path(ident["path"]))
    missing = [k for k in ("destination", "designer") if resolved[k] is None]
    return {"repo": ident, "resolved": resolved, "source": source,
            "matched_project": match.get("match") if match else None,
            "suggest": suggest, "missing": missing,
            "config_has_section": bool(section)}


_PLACEHOLDERS = {"이름", "담당자", "디자이너", "name", "designer", "todo", "-", "tbd", "없음"}


def _designer_from_templates(root: Path) -> list[str]:
    """이슈 템플릿의 `디자인:` 줄에서 담당자 후보. 최근 디자인 이슈 담당자는 agent 가 pro-github 로 본다."""
    found: list[str] = []
    d = root / ".github" / "ISSUE_TEMPLATE"
    if not d.is_dir():
        return found
    for f in sorted(d.glob("*")):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"디자인\**\s*[:：][ \t]*@?([^\s,*]+)", text):
            v = m.group(1).strip()
            # 템플릿 자리표시(`디자인: 이름` 등)를 담당자로 읽지 않는다 — 실측으로 걸렸다
            if v and v not in found and not v.startswith(("{", "[", "<")) \
                    and v.lower() not in _PLACEHOLDERS:
                found.append(v)
    return found


def cmd_config(args) -> int:
    root = Path(args.root).resolve()
    if args.action == "show":
        r = resolve_config(root)
        return emit({**r, "config_file": str(_config_path()),
                     "summary": (f"출력 {r['resolved']['destination'] or '미정'} · "
                                 f"디자이너 {r['resolved']['designer'] or '미정'} · "
                                 f"게시 전 확인 {'생략' if r['resolved']['auto_approve'] else '받음'}"),
                     "next": (None if not r["missing"] else
                              f"정해지지 않은 것: {', '.join(r['missing'])} — 사용자에게 한 번에 하나씩 묻고 "
                              "config set 으로 저장한다 (키 이름은 사용자에게 보이지 않는다)")})

    # set — 전체를 읽고 해당 키만 바꿔 쓴다 (config-rules.md §4). 다른 섹션을 날리지 않는다.
    changes = {}
    if args.destination is not None:
        if args.destination not in DESTINATIONS:
            return emit({"ok": False, "code": "bad_destination",
                         "error": f"destination 은 {' · '.join(DESTINATIONS)} 중 하나"})
        changes["destination"] = args.destination
    if args.designer is not None:
        changes["designer"] = args.designer
    if args.auto_approve is not None:
        changes["auto_approve"] = args.auto_approve == "true"
    if not changes:
        return emit({"ok": False, "code": "nothing_to_set",
                     "error": "--destination · --designer · --auto-approve 중 하나는 있어야 합니다"})

    config = _load_config()
    section = config.setdefault("design_brief", {})
    if args.scope == "default":
        section.update(changes)
        target = "default"
    else:
        ident = _repo_identity(root)
        key = ident["slug"] or ident["path"]   # GitHub 이 아니면 경로로 맞춘다
        projects = section.setdefault("projects", [])
        entry = next((p for p in projects if isinstance(p, dict) and
                      str(p.get("match", "")).lower() == key.lower()), None)
        if entry is None:
            entry = {"match": key}
            projects.append(entry)
        entry.update(changes)
        target = key
    f = _config_path()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return emit({"saved": changes, "scope": target, "resolved": resolve_config(root, config)["resolved"],
                 "summary": f"저장했다 ({target})"})


# =========================================================================
# get-output-path
# =========================================================================

def cmd_output_path(args) -> int:
    """이번 요청서 자리. 캡처는 pro-launch get-output-path --skill design-brief 로 같은 우산에 받는다."""
    try:
        from common.paths import resolve_output_path
    except ImportError:
        return emit({"ok": False, "code": "common_not_found",
                     "error": "scripts/common/paths.py 를 찾지 못했습니다"})
    r = resolve_output_path(SKILL_ID, args.title)
    if r.get("ok") is False:
        return emit(r)
    md = Path(r["path"])
    run_dir = md.parent / md.stem
    (run_dir / "board").mkdir(parents=True, exist_ok=True)
    return emit({"run_dir": str(run_dir), "board_dir": str(run_dir / "board"),
                 "brief_md": str(run_dir / "brief.md"), "gitignore": r.get("gitignore"),
                 "output_root": r.get("output_root"),
                 "summary": f"요청서 자리 {run_dir} (추적 제외 {r.get('gitignore')})",
                 "next": ("캡처는 pro-launch 로 받는다: launch_cli.py get-output-path --skill design-brief "
                          "(같은 제목) → 받은 env.sh 를 source 하면 $SHOT_DIR 가 이 우산 아래다")})


# =========================================================================
# board — 데이터 JSON → HTML (+ 주제별 PNG)
# =========================================================================
#
# PIL 로 좌표를 계산해 합치던 방식은 글자 배치를 여러 번 고쳐야 했다(확대 영역 두 번 수정).
# HTML 로 짜고 브라우저로 찍으면 글자 흐름은 브라우저가 맡는다.

TOPICS = [
    ("summary", "요약"), ("current", "현재 구현"), ("states", "상태"),
    ("alternatives", "대안 비교"), ("copy", "문구"), ("ui", "UI 요소"), ("impact", "개발 영향"),
]

_STATUS_TAG = {"done": ("구현됨", "done"), "temp": ("화면 임시", "temp"),
               "none": ("미구현", "none"), "missing": ("미구현", "none")}


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
        pass
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _img(path_str: str, base: Path, cls: str = "") -> str:
    p = Path(path_str)
    if not p.is_absolute():
        p = base / p
    if not p.is_file():
        return f'<div class="muted">그림 없음: {_e(path_str)}</div>'
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


def _figure(item: dict, base: Path) -> str:
    label = _e(item.get("label") or item.get("name"))
    zoom = " zoom" if item.get("zoom") else ""
    if item.get("image"):
        body = _img(item["image"], base)
    elif item.get("ascii"):
        body = f'<pre class="ascii">{_ascii_html(item["ascii"])}</pre>'
    else:
        body = '<div class="muted">캡처 없음</div>'
    return f'<figure class="{zoom.strip()}">{body}<figcaption>{label}</figcaption></figure>'


def _ul(items) -> str:
    return "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in items or []) + "</ul>" if items else ""


def _section(topic: str, title: str, inner: str) -> str:
    return f'<section class="topic" id="{topic}"><h2>{_e(title)}</h2>{inner}</section>'


def build_sections(data: dict, base: Path) -> list[tuple[str, str, str]]:
    """(주제 id, 제목, HTML). 데이터에 없는 주제는 만들지 않는다 — 빈 칸을 보여 주지 않는다."""
    out = []
    s = data.get("summary") or {}
    inner = ('<div class="banner">정답이 아니라 생각할 재료입니다. 대안·문구·요소 전부 바꿔도 됩니다.'
             + (f' {_e(s.get("note"))}' if s.get("note") else "") + "</div>")
    inner += "<dl class=\"kv\">"
    for k, label in (("what", "무엇을"), ("why", "왜"), ("status", "지금 상태"), ("recommend", "개발 쪽 추천")):
        if s.get(k):
            inner += f"<dt>{label}</dt><dd>{_e(s[k])}</dd>"
    inner += "</dl>"
    if s.get("must_keep"):
        inner += "<h3>꼭 지킬 것</h3><table><tr><th>무엇</th><th>출처</th></tr>" + "".join(
            f"<tr><td>{_e(m.get('rule') if isinstance(m, dict) else m)}</td>"
            f"<td class='muted'>{_e(m.get('source') if isinstance(m, dict) else '')}</td></tr>"
            for m in s["must_keep"]) + "</table>"
    out.append(("summary", "요약", inner))

    if data.get("current"):
        inner = '<div class="grid">' + "".join(_figure(c, base) for c in data["current"]) + "</div>"
        out.append(("current", "현재 구현", inner))

    if data.get("states"):
        rows = []
        for st in data["states"]:
            label, cls = _STATUS_TAG.get(st.get("status"), (st.get("status") or "?", "temp"))
            design = st.get("design")
            design_cell = ("" if design is None else
                           "<td>" + ("✅ 그려짐" if design is True else "❌ 없음" if design is False
                                     else _e(design)) + "</td>")
            shot = _figure({"image": st.get("image"), "ascii": st.get("ascii"),
                            "label": "렌더 실패 — ASCII" if st.get("render_failed") else ""}, base) \
                if (st.get("image") or st.get("ascii")) else '<span class="muted">—</span>'
            copy = ('<span class="tag none">문구 필요</span>' if st.get("copy_needed") else _e(st.get("copy")))
            rows.append(f"<tr><td>{_e(st.get('axis'))}</td><td><b>{_e(st.get('name'))}</b></td>"
                        f"<td><span class='tag {cls}'>{label}</span></td>{design_cell}"
                        f"<td>{copy}</td><td>{shot}</td></tr>")
        has_design = any(st.get("design") is not None for st in data["states"])
        head = ("<tr><th>축</th><th>상태</th><th>구현</th>" + ("<th>시안</th>" if has_design else "")
                + "<th>문구</th><th>화면</th></tr>")
        out.append(("states", "상태", f"<table>{head}{''.join(rows)}</table>"))

    if data.get("alternatives"):
        cards = []
        for a in data["alternatives"]:
            rec = ' <span class="tag rec">개발 쪽 추천</span>' if a.get("recommended") else ""
            pics = "".join(_figure({"image": im, "label": ""}, base) for im in a.get("images") or [])
            if a.get("image"):
                pics = _figure({"image": a["image"], "label": ""}, base) + pics
            if a.get("zoom"):
                pics += _figure({"image": a["zoom"], "label": "확대", "zoom": True}, base)
            if a.get("ascii"):
                # 렌더할 코드가 아직 없는 안(새 화면 등) — 무엇이 어디 있는지만 전한다
                pics += _figure({"ascii": a["ascii"], "label": "ASCII — 글꼴·간격·색은 담지 못한다"}, base)
            cards.append(f'<div class="alt"><h3>{_e(a.get("id"))}안 · {_e(a.get("name"))}{rec}</h3>'
                         f'<div class="grid">{pics}</div>'
                         f'<b>장점</b>{_ul(a.get("pros"))}<b>약점</b>{_ul(a.get("cons"))}'
                         f'<b>개발 영향</b><p>{_e(a.get("dev_impact") or "없음")}</p></div>')
        out.append(("alternatives", "대안 비교", '<div class="grid">' + "".join(cards) + "</div>"))

    if data.get("copy"):
        rows = []
        for c in data["copy"]:
            if c.get("legal"):
                cand = '<span class="tag legal">법적 문구 — 바꾸면 안 됨</span>'
            elif c.get("needed"):
                cand = '<span class="tag none">문구 필요</span>'
            else:
                cand = _ul(c.get("candidates"))
            rows.append(f"<tr><td>{_e(c.get('where'))}</td><td>{_e(c.get('current'))}</td>"
                        f"<td>{cand}</td><td class='muted'>{_e(c.get('reason'))}</td></tr>")
        out.append(("copy", "문구", "<table><tr><th>자리</th><th>현재</th><th>후보</th><th>이유</th></tr>"
                    + "".join(rows) + "</table>"))

    if data.get("ui"):
        rows = "".join(
            f"<tr><td>{_e(u.get('shape'))}</td><td>{_ul(u.get('candidates'))}</td>"
            f"<td>{_ul(u.get('existing'))}</td><td>{_ul(u.get('new'))}</td></tr>" for u in data["ui"])
        out.append(("ui", "UI 요소", "<table><tr><th>데이터 모양</th><th>후보</th>"
                    "<th>레포에 있는 컴포넌트</th><th>새 컴포넌트</th></tr>" + rows + "</table>"))

    if data.get("impact"):
        rows = "".join(f"<tr><td>{_e(i.get('choice'))}</td><td>{_e(i.get('work'))}</td></tr>"
                       for i in data["impact"])
        out.append(("impact", "개발 영향", "<table><tr><th>고르면</th><th>따로 필요한 개발</th></tr>"
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
    doc = (tpl.replace("{{TITLE}}", _e(data.get("title") or "디자인 요청서"), 1)
              .replace("<!--NAV-->", nav, 1).replace("<!--SECTIONS-->", body, 1)
              .replace("</body>", _image_script() + "\n</body>", 1))
    return doc, [t for t, _, _ in sections]


def _require_playwright():
    sp = venv_site_packages()
    if sp and str(sp) not in sys.path:
        sys.path.insert(0, str(sp))
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def shoot_topics(html_file: Path, out_dir: Path, topics: list[str], scale: int = 2) -> tuple[list[str], str | None]:
    """주제(섹션)마다 PNG 한 장. pro-launch 가 받아 둔 Chromium 을 쓴다 — 따로 설치하지 않는다."""
    sync_playwright = _require_playwright()
    if sync_playwright is None:
        return [], "browser_missing"
    files = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1448, "height": 900}, device_scale_factor=scale)
            page.goto(html_file.resolve().as_uri())
            page.evaluate("document.fonts.ready")
            page.wait_for_function("[...document.images].every(i => i.complete)", timeout=30000)
            page.add_style_tag(content="nav{display:none!important}")   # 목차는 그림에 필요 없다
            for n, topic in enumerate(topics, 1):
                el = page.locator(f"section#{topic}")
                box = el.bounding_box()
                if not box:
                    continue
                f = out_dir / f"{n:02d}_{topic}.png"
                el.screenshot(path=str(f))
                files.append(str(f))
            browser.close()
    except Exception as e:  # 브라우저 파일이 없거나 실행이 막힌 경우
        return files, f"browser_failed: {str(e).splitlines()[0][:200]}"
    return files, None


def _png_width(f: Path) -> int:
    with f.open("rb") as fh:
        head = fh.read(24)
    return int.from_bytes(head[16:20], "big") if head[:8] == b"\x89PNG\r\n\x1a\n" else 0


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
    if data.get("states"):
        lines += ["", "## 상태", "", "| 축 | 상태 | 구현 | 문구 |", "|---|---|---|---|"]
        for st in data["states"]:
            label = _STATUS_TAG.get(st.get("status"), (st.get("status") or "?", ""))[0]
            copy = "**문구 필요**" if st.get("copy_needed") else (st.get("copy") or "")
            lines.append(f"| {_c(st.get('axis'))} | {_c(st.get('name'))} | {label} | {_c(copy)} |")
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


def cmd_board(args) -> int:
    data_f = Path(args.data)
    try:
        data = json.loads(data_f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return emit({"ok": False, "code": "bad_data", "error": f"데이터 JSON 을 읽지 못했습니다: {e}"})
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = data_f.parent   # 데이터 안의 상대 그림 경로는 데이터 파일 기준
    doc, topics = render_html(data, base)
    html_f = out_dir / "board.html"
    html_f.write_text(doc, encoding="utf-8")

    payload = {"html": str(html_f), "topics": topics, "png": []}
    if args.png:
        files, err = shoot_topics(html_f, out_dir, topics, scale=args.scale)
        payload["png"] = files
        too_wide = [f for f in files if _png_width(Path(f)) > MAX_PNG_WIDTH]
        if too_wide:
            payload["too_wide"] = too_wide
        if err:
            # 브라우저가 없으면 멈추지 않는다 — md 표 + 원본 캡처로 낸다 (설계 §6)
            payload.update({"ok": False, "code": "browser_missing" if err == "browser_missing" else "png_failed",
                            "error": err,
                            "next": ("PNG 없이 진행한다: 보드 HTML 을 그대로 쓰거나(markdown/html 출력) "
                                     "원본 캡처 + md 표로 낸다. 브라우저가 필요하면 pro-launch web setup "
                                     "(먼저 사용자에게 묻는다)")})
            payload["summary"] = f"HTML 만 만들었다 ({err})"
            return emit(payload)
    if args.md:
        md_f = out_dir / "brief.md"
        md_f.write_text(render_markdown(data, payload["png"], out_dir), encoding="utf-8")
        payload["md"] = str(md_f)
    payload["summary"] = (f"보드 {len(topics)}주제 · HTML" + (f" · PNG {len(payload['png'])}장" if args.png else "")
                          + (" · md" if args.md else ""))
    payload["next"] = "Read 로 PNG 를 열어 확인한 뒤 게시 전 승인을 받는다"
    return emit(payload)


# =========================================================================
# copy-lint — 기계적으로 짚을 수 있는 것만. 좋은 문구는 agent 가 쓴다
# =========================================================================

_TRANSLATIONESE = [
    (r"하실 수 있습니다", "번역투 — '~할 수 있어요' 처럼 짧게"),
    (r"되었습니다", "피동·딱딱함 — '~했어요'"),
    (r"에 대한", "번역투 '에 대한' — 빼도 뜻이 통하는지"),
    (r"을 통해|를 통해", "번역투 '~을 통해'"),
    (r"것입니다", "딱딱함 — 해요체면 '~예요'"),
]
_HYPE = ["혁신적", "완벽한", "완벽하게", "최고의", "놀라운", "획기적", "압도적"]


def lint_text(text: str, banned: list[str]) -> list[str]:
    found = []
    if "—" in text or "–" in text:
        found.append("em dash — AI 가 쓴 티가 난다. 쉼표나 문장 나누기로")
    if text.count("·") >= 2:
        found.append("가운뎃점(·) 남발")
    for pat, why in _TRANSLATIONESE:
        if re.search(pat, text):
            found.append(why)
    for w in _HYPE:
        if w in text:
            found.append(f"과장 '{w}'")
    for w in banned:
        if w and w in text:
            found.append(f"레포에서 쓰지 않기로 한 말 '{w}'")
    return found


def cmd_copy_lint(args) -> int:
    try:
        rows = json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return emit({"ok": False, "code": "bad_file", "error": str(e)})
    if isinstance(rows, dict):
        rows = rows.get("copy") or []
    banned = []
    if args.banned:
        bf = Path(args.banned)
        banned = ([l.strip() for l in bf.read_text(encoding="utf-8").splitlines() if l.strip()]
                  if bf.is_file() else [w.strip() for w in args.banned.split(",") if w.strip()])
    issues, checked = [], 0
    for r in rows:
        if r.get("legal"):
            continue   # 법적 문구는 후보를 내지 않는다 — 검사 대상도 아니다
        for kind, texts in (("current", [r.get("current")]), ("candidate", r.get("candidates") or [])):
            for t in texts:
                if not t:
                    continue
                checked += 1
                hits = lint_text(str(t), banned)
                if hits:
                    issues.append({"where": r.get("where"), "kind": kind, "text": t, "problems": hits})
    cand_issues = [i for i in issues if i["kind"] == "candidate"]
    return emit({"ok": not cand_issues, "code": "ok" if not cand_issues else "candidate_issues",
                 "checked": checked, "issues": issues,
                 "summary": f"{checked}개 문장 중 {len(issues)}개에 짚을 것"
                            + (f" (후보 {len(cand_issues)}개)" if cand_issues else ""),
                 "next": ("후보에 걸린 것은 고쳐서 다시 돌린다. 현재 문구에 걸린 것은 '이유' 칸의 재료다"
                          if issues else None)})


# =========================================================================
# ascii — 등폭 · 박스 문자 · 한글 폭 보정
# =========================================================================

def text_width(s: str) -> int:
    """화면에 차지하는 칸 수. 한글·전각은 두 칸 — 안 세면 오른쪽 선이 어긋난다."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _fit(s: str, width: int, align: str) -> str:
    while text_width(s) > width:
        s = s[:-1]
    gap = width - text_width(s)
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    if align == "right":
        return " " * gap + s
    return s + " " * gap


def render_ascii(spec: dict) -> str:
    width = int(spec.get("width") or 30)
    lines = ["┌" + "─" * width + "┐"]
    if spec.get("title"):
        lines.append("│" + _fit(" " + str(spec["title"]), width, "left") + "│")
        lines.append("├" + "─" * width + "┤")
    for row in spec.get("rows") or []:
        if row == "---":
            lines.append("├" + "─" * width + "┤")
            continue
        if isinstance(row, dict):
            text, align = str(row.get("text", "")), row.get("align", "left")
        else:
            text, align = str(row), "left"
        lines.append("│" + _fit(text, width, align) + "│")
    lines.append("└" + "─" * width + "┘")
    if spec.get("caption"):
        lines.append("  " + str(spec["caption"]))
    return "\n".join(lines)


def cmd_ascii(args) -> int:
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8")) if Path(args.spec).is_file() \
            else json.loads(args.spec)
    except (OSError, json.JSONDecodeError) as e:
        return emit({"ok": False, "code": "bad_spec", "error": str(e)})
    text = render_ascii(spec)
    body = text.split("\n")
    widths = {text_width(l) for l in body[:-1 if spec.get("caption") else None]}
    out = {"ascii": text, "width": int(spec.get("width") or 30) + 2, "aligned": len(widths) == 1,
           "summary": f"{len(body)}줄 와이어"}
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        out["file"] = args.out
    return emit(out)


# =========================================================================
# 인자
# =========================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="design_brief_cli", description="디자인 요청서를 조립한다")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("config", help="design_brief 설정 해석 / 저장")
    p.add_argument("action", choices=["show", "set"])
    p.add_argument("--root", default=".")
    p.add_argument("--scope", choices=["project", "default"], default="project",
                   help="set: 이 레포만(project) 또는 모든 레포 기본값(default)")
    p.add_argument("--destination", default=None, help=f"set: {' · '.join(DESTINATIONS)}")
    p.add_argument("--designer", default=None, help="set: 디자이너 GitHub 아이디 또는 이름")
    p.add_argument("--auto-approve", choices=["true", "false"], default=None,
                   help="set: 게시 전 확인을 생략할지")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("get-output-path", help="이번 요청서의 산출물 자리")
    p.add_argument("--title", default=None)
    p.set_defaults(func=cmd_output_path)

    p = sub.add_parser("board", help="데이터 JSON → 보드 HTML (+ 주제별 PNG)")
    p.add_argument("--data", required=True, help="보드 데이터 JSON (SKILL.md 의 형식)")
    p.add_argument("--out", required=True, help="보드를 쓸 폴더")
    p.add_argument("--png", action="store_true", help="주제별 PNG 도 만든다 (pro-launch 의 Chromium)")
    p.add_argument("--scale", type=int, default=2, help="PNG 배율 (기본 2 — 폭 약 2900px)")
    p.add_argument("--md", action="store_true", help="markdown 출력용 brief.md 도 만든다 (PNG 링크 포함)")
    p.set_defaults(func=cmd_board)

    p = sub.add_parser("copy-lint", help="문구 후보의 기계적 검사")
    p.add_argument("--file", required=True, help="문구표 JSON (보드 데이터의 copy 배열 또는 보드 데이터 전체)")
    p.add_argument("--banned", default=None, help="쓰지 않기로 한 말 — 파일(한 줄에 하나) 또는 쉼표 목록")
    p.set_defaults(func=cmd_copy_lint)

    p = sub.add_parser("ascii", help="박스 문자 와이어 (한글 폭 보정)")
    p.add_argument("--spec", required=True, help="와이어 JSON 파일 또는 JSON 문자열")
    p.add_argument("--out", default=None, help="저장할 파일")
    p.set_defaults(func=cmd_ascii)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        if e.code in (0, None):
            raise
        return emit({"ok": False, "code": "bad_args", "error": "인자가 올바르지 않습니다",
                     "next": "design_brief_cli.py <서브커맨드> --help"})
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
