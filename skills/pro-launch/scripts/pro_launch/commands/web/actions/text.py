"""`web text` — 보이는 글자를 읽는다 (스크린샷보다 싸다). --grep 이면 맞는 줄과 앞뒤만 (#891)."""
from __future__ import annotations


from pro_launch.commands.web.session import safe_title
from pro_launch.registry import Action


def grep_lines(lines: list[str], needle: str, around: int) -> tuple[str, int]:
    """대소문자 무시 부분 문자열로 맞는 줄 + 앞뒤 around 줄. 떨어진 묶음은 '…' 줄로 가른다. (글, 맞은 줄 수)"""
    lowered = needle.lower()
    hits = [i for i, line in enumerate(lines) if lowered in line.lower()]
    keep: set[int] = set()
    for i in hits:
        keep.update(range(max(0, i - around), min(len(lines), i + around + 1)))
    out_lines: list[str] = []
    previous = None
    for i in sorted(keep):
        if previous is not None and i != previous + 1:
            out_lines.append("…")
        out_lines.append(lines[i])
        previous = i
    return "\n".join(out_lines), len(hits)


def _web_text(page, args) -> dict:
    loc = page.locator(args.selector).first if args.selector else page.locator("body")
    if args.selector and page.locator(args.selector).count() == 0:
        return {"ok": False, "code": "selector_not_found", "action": "text", "url": page.url,
                "error": f"{args.selector} 에 맞는 요소가 없습니다", "next": "web find --text <글자>"}
    raw = loc.inner_text(timeout=args.timeout * 1000)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if args.grep:
        return _grep_payload(page, args, lines)
    text = "\n".join(lines)
    cut = len(text) > args.max_chars
    return {"action": "text", "text": text[:args.max_chars], "truncated": cut, "chars": len(text),
            "url": page.url, "title": safe_title(page),
            "summary": f"글자 {len(text)}자" + (f" (앞 {args.max_chars}자만)" if cut else ""),
            "next": "web find --text <누를 것의 글자>" + ("  # 잘렸으면 --selector 로 범위를 좁힌다" if cut else "")}


def _grep_payload(page, args, lines: list[str]) -> dict:
    around = max(0, args.around)
    text, match_count = grep_lines(lines, args.grep, around)
    cut = len(text) > args.max_chars
    return {"action": "text", "grep": args.grep, "around": around, "match_count": match_count,
            "text": text[:args.max_chars], "truncated": cut, "total_lines": len(lines),
            "url": page.url, "title": safe_title(page),
            "summary": f"'{args.grep}' {match_count}줄 일치 (앞뒤 {around}줄)",
            "next": ("web find --text <누를 것의 글자>" if match_count
                     else "web text  # 일치가 없다 — 전체 글자를 읽고 다른 낱말로 찾는다")}


def configure(p) -> None:
    p.add_argument("--max-chars", dest="max_chars", type=int, default=3000, help="돌려줄 최대 글자 수")
    p.add_argument("--grep", default=None, help="이 글자가 든 줄만 (대소문자 무시, 정규식 아님)")
    p.add_argument("--around", type=int, default=1, help="--grep: 맞은 줄 앞뒤로 함께 줄 줄 수 (기본 1)")


def execute(page, args, state: dict) -> dict:
    return _web_text(page, args)


ACTION = Action(name="text", run=execute, configure=configure, options=("selector", "timeout"),
                help="보이는 글자를 읽는다 — 스크린샷보다 싸다",
                example='web text --grep "error" --around 2')
