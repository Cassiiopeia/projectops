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
        return emit({"ok": False, "code": "bad_data", "error": f"데이터 JSON 을 읽지 못했습니다: {e}"})
    if not isinstance(data, dict):
        return emit({"ok": False, "code": "bad_data",
                     "error": f"보드 데이터는 JSON 객체여야 합니다 ({type(data).__name__})",
                     "next": "SKILL.md 의 보드 데이터 형식(summary·screens·alternatives …)을 따른다"})
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
    if warns:
        payload["next"] = (f"게시 전에 걸릴 것 {len(warns)}건 (preflight) — 고친 뒤 다시 조립한다. "
                           "렌더 캡처만 근거인 사실은 실기기·운영 API 로 확인한다")
        if args.strict:
            payload.update({"ok": False, "code": "preflight_failed"})
    else:
        payload["next"] = "Read 로 PNG 를 열어 확인한 뒤 게시 전 승인을 받는다"
    return emit(payload)
