"""`web text` — 보이는 글자를 읽는다 (스크린샷보다 싸다). --grep 이면 맞는 줄과 앞뒤만 (#891)."""
from __future__ import annotations


from pro_launch.commands.web.frames import frame_scope
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
    # --frame 이면 그 iframe 문서의 글자 (#877)
    scope, failure = frame_scope(page, args, "text")
    if failure:
        return failure
    loc = scope.locator(args.selector).first if args.selector else scope.locator("body")
    if args.selector and scope.locator(args.selector).count() == 0:
        return {"ok": False, "code": "selector_not_found", "action": "text", "url": page.url,
                "error": f"No element matches {args.selector}", "next": "web find --text <text>"}
    raw = loc.inner_text(timeout=args.timeout * 1000)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if args.grep:
        return _grep_payload(page, args, lines)
    text = "\n".join(lines)
    cut = len(text) > args.max_chars
    return {"action": "text", "text": text[:args.max_chars], "truncated": cut, "chars": len(text),
            "url": page.url, "title": safe_title(page),
            "summary": f"{len(text)} chars" + (f" (first {args.max_chars} only)" if cut else ""),
            "next": "web find --text <text of what to click>" + ("  # if cut off, narrow it with --selector" if cut else "")}


def _grep_payload(page, args, lines: list[str]) -> dict:
    around = max(0, args.around)
    text, match_count = grep_lines(lines, args.grep, around)
    cut = len(text) > args.max_chars
    return {"action": "text", "grep": args.grep, "around": around, "match_count": match_count,
            "text": text[:args.max_chars], "truncated": cut, "total_lines": len(lines),
            "url": page.url, "title": safe_title(page),
            "summary": f"'{args.grep}' matched {match_count} lines ({around} lines of context)",
            "next": ("web find --text <text of what to click>" if match_count
                     else "web text  # no match — read all the text and search with other words")}


def configure(p) -> None:
    p.add_argument("--max-chars", dest="max_chars", type=int, default=3000, help="Maximum number of characters to return")
    p.add_argument("--grep", default=None, help="Only lines containing this text (case-insensitive, not a regex)")
    p.add_argument("--around", type=int, default=1, help="--grep: lines of context before and after each match (default 1)")


def execute(page, args, state: dict) -> dict:
    return _web_text(page, args)


ACTION = Action(name="text", run=execute, configure=configure, options=("selector", "timeout", "frame"),
                help="Read the visible text — cheaper than a screenshot",
                example='web text --grep "error" --around 2')
