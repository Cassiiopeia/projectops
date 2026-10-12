"""`web click` — 고른 요소 하나만 누르고 무엇이 바뀌었는지 돌려준다."""
from __future__ import annotations


from pro_launch.commands.web.session import settle
from pro_launch.commands.web.targets import DESCRIBE_JS, REF_ATTR, is_mutating_target
from pro_launch.registry import Action


def _web_click(page, args, state: dict) -> dict:
    """고른 요소 하나만 누르고, 무엇을 눌렀고 무엇이 바뀌었는지 돌려준다."""
    if args.ref is None and not args.selector:
        return {"ok": False, "code": "target_required", "action": "click",
                "error": "--ref 나 --selector 가 필요합니다",
                "next": "web find --text <글자>  # 후보 번호를 받아 --ref 로 누른다"}
    target = f'[{REF_ATTR}="{args.ref}"]' if args.ref is not None else args.selector
    loc = page.locator(target)
    if loc.count() == 0:
        if args.ref is not None:
            return {"ok": False, "code": "ref_stale", "action": "click", "url": page.url,
                    "error": f"ref {args.ref} 이 화면에 없습니다 (이동·다시 그리기로 사라졌다)",
                    "next": "web find  # 지금 화면에서 다시 고른다"}
        return {"ok": False, "code": "selector_not_found", "action": "click", "url": page.url,
                "error": f"{args.selector} 에 맞는 요소가 없습니다", "next": "web find --text <글자>"}
    el = loc.first
    info = el.evaluate(DESCRIBE_JS)
    label = f"{info.get('text') or ''} {info.get('aria') or ''}"
    if state.get("readonly") and is_mutating_target(info) and not args.confirm_mutating:
        return {"ok": False, "code": "mutating_blocked", "action": "click", "clicked": None,
                "target": info, "url": page.url,
                "error": f"읽기 전용 세션이라 '{label.strip()[:60]}' 을 누르지 않았습니다",
                "next": "정말 눌러야 하면 사용자에게 무엇이 바뀌는지 말하고 승인받은 뒤 --confirm-mutating 을 붙인다"}
    before_url, before_title = page.url, page.title()
    el.click(timeout=args.timeout * 1000)
    waited = None
    try:
        if args.expect_url:
            waited = "url"
            page.wait_for_url(lambda u: args.expect_url in u, timeout=args.timeout * 1000)
        elif args.expect_text:
            waited = "text"
            page.get_by_text(args.expect_text).first.wait_for(state="visible", timeout=args.timeout * 1000)
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
                "url": page.url, "title": page.title(),
                "error": f"눌렀지만 기대한 {'주소' if waited == 'url' else '글자'}가 {args.timeout}초 안에 나오지 않았습니다",
                "next": "web text  # 지금 화면을 읽고, 엉뚱한 것을 눌렀으면 web find 로 다시 고른다"}
    settle(page, state, args.timeout)
    after_url, after_title = page.url, page.title()
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
    p.add_argument("--ref", type=int, default=None, help="click: web find 가 준 번호. 선택자 추측 대신 이것을 쓴다")
    p.add_argument("--expect-url", dest="expect_url", default=None,
                   help="click: 누른 뒤 주소에 이 글자가 들어올 때까지 기다린다. 안 오면 실패")
    p.add_argument("--expect-text", dest="expect_text", default=None,
                   help="click: 누른 뒤 이 글자가 보일 때까지 기다린다. 안 오면 실패")
    p.add_argument("--confirm-mutating", dest="confirm_mutating", action="store_true",
                   help="click: 읽기 전용 세션에서도 누른다 (사용자 승인을 받은 뒤에만)")


ACTION = Action(name="click", run=_web_click, configure=configure)
