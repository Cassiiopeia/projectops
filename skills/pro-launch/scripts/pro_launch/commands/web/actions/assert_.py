"""`web assert` — check that a URL, text or element is present."""
from __future__ import annotations


from pro_launch.commands.web.frames import frame_scope
from pro_launch.commands.web.url_match import url_without_query
from pro_launch.registry import Action


def execute(page, args, state: dict) -> dict:
    # With --frame, text and elements are checked inside that iframe (#877). The URL is always the tab URL
    scope, failure = frame_scope(page, args, "assert")
    if failure:
        return failure
    checks = []
    # Compare the URL without ?query and #fragment (same rule as wait --url-contains, #1191)
    if args.url:
        checks.append({"expect_url": args.url, "got": page.url,
                       "ok": args.url in url_without_query(page.url, args.url)})
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
