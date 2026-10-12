"""`web text` — 보이는 글자를 읽는다 (스크린샷보다 싸다)."""
from __future__ import annotations


from pro_launch.commands.web.session import safe_title
from pro_launch.registry import Action


def _web_text(page, args) -> dict:
    loc = page.locator(args.selector).first if args.selector else page.locator("body")
    if args.selector and page.locator(args.selector).count() == 0:
        return {"ok": False, "code": "selector_not_found", "action": "text", "url": page.url,
                "error": f"{args.selector} 에 맞는 요소가 없습니다", "next": "web find --text <글자>"}
    raw = loc.inner_text(timeout=args.timeout * 1000)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    text = "\n".join(lines)
    cut = len(text) > args.max_chars
    return {"action": "text", "text": text[:args.max_chars], "truncated": cut, "chars": len(text),
            "url": page.url, "title": safe_title(page),
            "summary": f"글자 {len(text)}자" + (f" (앞 {args.max_chars}자만)" if cut else ""),
            "next": "web find --text <누를 것의 글자>" + ("  # 잘렸으면 --selector 로 범위를 좁힌다" if cut else "")}


def configure(p) -> None:
    p.add_argument("--max-chars", dest="max_chars", type=int, default=3000, help="text: 돌려줄 최대 글자 수")


def execute(page, args, state: dict) -> dict:
    return _web_text(page, args)


ACTION = Action(name="text", run=execute, configure=configure)
