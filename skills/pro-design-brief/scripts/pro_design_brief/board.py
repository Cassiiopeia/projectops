"""board: 데이터 JSON > 보드 HTML (+ PNG · markdown)"""
from __future__ import annotations

import json
from pathlib import Path

from common.emit import emit

from pro_design_brief.board_capture import _png_width, shoot_topics
from pro_design_brief.board_html import render_html
from pro_design_brief.board_markdown import preflight, render_markdown
from pro_design_brief.settings import MAX_PNG_WIDTH


def cmd_board(args) -> int:
    data_f = Path(args.data)
    try:
        data = json.loads(data_f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return emit({"ok": False, "code": "bad_data", "error": f"Could not read the data JSON: {e}"})
    if not isinstance(data, dict):
        return emit({"ok": False, "code": "bad_data",
                     "error": f"Board data must be a JSON object ({type(data).__name__})",
                     "next": "Follow the board data format in SKILL.md (summary, screens, alternatives, ...)"})
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = data_f.parent   # 데이터 안의 상대 그림 경로는 데이터 파일 기준
    doc, topics = render_html(data, base)
    html_f = out_dir / "board.html"
    html_f.write_text(doc, encoding="utf-8")

    warns = preflight(data)
    payload = {"html": str(html_f), "topics": topics, "png": [], "preflight": warns}
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
                            "next": ("Continue without PNGs: use the board HTML as is (markdown/html output) "
                                     "or post the original captures with an md table. If a browser is needed, "
                                     "run pro-launch web setup (ask the user first)")})
            payload["summary"] = f"Built the HTML only ({err})"
            return emit(payload)
    if args.md:
        md_f = out_dir / "brief.md"
        md_f.write_text(render_markdown(data, payload["png"], out_dir), encoding="utf-8")
        payload["md"] = str(md_f)
    payload["summary"] = (f"Board: {len(topics)} topics · HTML" + (f" · {len(payload['png'])} PNGs" if args.png else "")
                          + (" · md" if args.md else ""))
    if warns:
        payload["next"] = (f"{len(warns)} issue(s) to fix before posting (preflight): fix them and assemble again. "
                           "Confirm facts backed only by render captures on a real device or the production API")
        if args.strict:
            payload.update({"ok": False, "code": "preflight_failed"})
    else:
        payload["next"] = "Open the PNGs with Read to check them, then get approval before posting"
    return emit(payload)
