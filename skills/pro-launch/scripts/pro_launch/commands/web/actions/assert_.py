"""`web assert` — 주소·글자·요소가 있는지 확인한다."""
from __future__ import annotations


from pro_launch.commands.web.frames import frame_scope
from pro_launch.registry import Action


def execute(page, args, state: dict) -> dict:
    # 글자·요소는 --frame 이면 그 iframe 안에서 본다 (#877). 주소는 언제나 탭 주소
    scope, failure = frame_scope(page, args, "assert")
    if failure:
        return failure
    checks = []
    if args.url:
        checks.append({"expect_url": args.url, "got": page.url,
                       "ok": args.url in page.url})
    if args.text:
        checks.append({"expect_text": args.text,
                       "ok": scope.get_by_text(args.text).count() > 0})
    if args.selector:
        checks.append({"expect_selector": args.selector,
                       "ok": scope.locator(args.selector).count() > 0})
    if not checks:
        return {"ok": False, "code": "nothing_to_assert",
                "error": "Give at least one of --url · --text · --selector"}
    passed = all(c["ok"] for c in checks)
    return {"action": "assert", "checks": checks, "ok": passed, "url": page.url,
            "code": "ok" if passed else "assert_failed",
            "summary": "Check passed" if passed else "Check failed"}


ACTION = Action(name="assert", run=execute, options=("url", "text", "selector", "frame"),
                help="Check that a URL, text or element is present",
                example='web assert --url /home --text "Welcome"')
