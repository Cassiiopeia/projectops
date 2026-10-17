"""`web goto` — 주소로 이동한다."""
from __future__ import annotations


from pro_launch.commands.web.session import done_payload, settle
from pro_launch.registry import Action


def execute(page, args, state: dict) -> dict:
    if not args.url:
        return {"ok": False, "code": "url_required", "error": "--url 이 필요합니다"}
    resp = page.goto(args.url, wait_until="domcontentloaded", timeout=max(args.timeout, 30) * 1000)
    nav_status = resp.status if resp is not None else None
    settle(page, state, args.timeout)
    payload = done_payload(args.action, page)
    # 404·500 페이지로 가도 이동 자체는 성공이다 — 상태코드를 함께 줘서 호출한 쪽이 판단하게 한다 (#711)
    payload["status"] = nav_status
    if nav_status is not None and nav_status >= 400:
        payload["summary"] += f" (HTTP {nav_status} — 오류 응답)"
        payload["http_error"] = True
    return payload


ACTION = Action(name="goto", run=execute, options=("url", "timeout"),
                help="주소로 이동한다", example="web goto --url http://localhost:3000/items")
