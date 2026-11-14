"""`web console` — read the console log collected while the page loaded."""
from __future__ import annotations


from pro_launch.registry import Action


def execute(page, args, state: dict) -> dict:
    # **Read what was collected**, not listen (#625)
    try:
        logs = page.evaluate("window.__projectops_console || null")
    except Exception:
        logs = None
    if logs is None:
        return {"ok": False, "code": "console_hook_missing",
                "error": "This page has no console records",
                "hint": "The hook is installed now. Reopen with `web goto` and "
                        "records, load errors included, are collected from then on", "url": page.url}
    errs = [l for l in logs if l.get("type") == "error"]
    return {"action": "console", "logs": logs[-50:], "error_count": len(errs),
            "total": len(logs), "url": page.url,
            "summary": f"Console {len(logs)} lines ({len(errs)} errors) — since page load",
            "next": ("Errors mean it does not pass, even if the screen looks fine"
                     if errs else None)}


ACTION = Action(name="console", run=execute, options=(),
                help="Read the console records collected since the page loaded", example="web console")
