"""`web console` — 페이지가 로드되는 동안 쌓인 콘솔 기록을 읽는다."""
from __future__ import annotations


from pro_launch.registry import Action


def execute(page, args, state: dict) -> dict:
    # 듣는 게 아니라 **쌓인 것을 읽는다** (#625)
    try:
        logs = page.evaluate("window.__projectops_console || null")
    except Exception:
        logs = None
    if logs is None:
        return {"ok": False, "code": "console_hook_missing",
                "error": "이 페이지에는 콘솔 기록이 없습니다",
                "hint": "훅을 지금 심었습니다. `web goto` 로 다시 들어가면 "
                        "그때부터 로드 오류까지 모입니다", "url": page.url}
    errs = [l for l in logs if l.get("type") == "error"]
    return {"action": "console", "logs": logs[-50:], "error_count": len(errs),
            "total": len(logs), "url": page.url,
            "summary": f"콘솔 {len(logs)}줄 (오류 {len(errs)}) — 로드 시점부터",
            "next": ("오류가 있으면 화면이 멀쩡해도 통과가 아닙니다"
                     if errs else None)}


ACTION = Action(name="console", run=execute, options=(),
                help="페이지가 로드되는 동안 쌓인 콘솔 기록을 읽는다", example="web console")
