"""`web click` — 고른 요소 하나만 누르고 무엇이 바뀌었는지 돌려준다."""
from __future__ import annotations


from pro_launch.commands.web.session import safe_title, settle
from pro_launch.commands.web.element import locate_target, outcome_wait_seconds, perform_on_target, target_wait_seconds
from pro_launch.registry import Action


def _web_click(page, args, state: dict) -> dict:
    """고른 요소 하나만 누르고, 무엇을 눌렀고 무엇이 바뀌었는지 돌려준다."""
    el, info, failure = locate_target(page, args, state, "click")
    if failure:
        return failure
    before_url, before_title = page.url, safe_title(page)
    failure = perform_on_target(page, args, "click", info, lambda: el.click(timeout=target_wait_seconds(args) * 1000))
    if failure:
        return failure
    outcome_seconds = outcome_wait_seconds(args)
    waited = None
    try:
        if args.expect_url:
            waited = "url"
            page.wait_for_url(lambda u: args.expect_url in u, timeout=outcome_seconds * 1000)
        elif args.expect_text:
            waited = "text"
            page.get_by_text(args.expect_text).first.wait_for(state="visible", timeout=outcome_seconds * 1000)
        else:
            # 기대를 안 줬으면 짧게만 기다린다 — SPA 는 주소가 늦게 바뀐다
            try:
                page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass
            page.wait_for_timeout(800)
    except Exception:
        return {"ok": False, "code": "expect_not_met", "action": "click", "clicked": info,
                "expected": args.expect_url or args.expect_text,
                "before": {"url": before_url, "title": before_title},
                "url": page.url, "title": safe_title(page),
                "error": f"눌렀지만 기대한 {'주소' if waited == 'url' else '글자'}가 {outcome_seconds}초 안에 나오지 않았습니다",
                "next": "web text  # 지금 화면을 읽고, 엉뚱한 것을 눌렀으면 web find 로 다시 고른다"}
    settle(page, state, outcome_seconds)
    after_url, after_title = page.url, safe_title(page)
    changed = after_url != before_url or after_title != before_title
    payload = {"action": "click", "clicked": info, "changed": changed,
               "before": {"url": before_url, "title": before_title},
               "url": after_url, "title": after_title,
               "summary": f"'{(info.get('text') or info.get('aria') or info.get('tag'))[:40]}' 클릭 → "
                          + ("주소·제목이 바뀌었다" if changed else "주소·제목 그대로")}
    if not changed and not (args.expect_url or args.expect_text):
        # 체크박스·펼치기처럼 제자리에서 바뀌는 것일 수도 있다 — 실패로 단정하지 않고 확인을 시킨다
        payload["next"] = "의도한 결과가 맞는지 web text / web assert 로 확인한다. 아니면 web find 로 다시 고른다"
    else:
        payload["next"] = "web text  # 바뀐 화면을 읽는다"
    return payload


def configure(p) -> None:
    p.add_argument("--expect-url", dest="expect_url", default=None,
                   help="누른 뒤 주소에 이 글자가 들어올 때까지 기다린다. 안 오면 실패")
    p.add_argument("--expect-text", dest="expect_text", default=None,
                   help="누른 뒤 이 글자가 보일 때까지 기다린다. 안 오면 실패")


ACTION = Action(name="click", run=_web_click, configure=configure,
                options=("ref", "selector", "target_timeout", "confirm_mutating"),
                help="고른 요소 하나만 누르고 무엇이 바뀌었는지 돌려준다",
                example="web click --ref 3 --expect-url /home")
