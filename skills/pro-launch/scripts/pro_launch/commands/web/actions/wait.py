"""`web wait` — 조건이 맞을 때까지 기다린다: 주소 · 글자 · 사라짐 · 요소 (#880).

다른 기기의 2단계 승인 · 업로드 끝 · 저장 토스트 · 주소 바뀜을 고정 sleep 이나 text 반복 대신 기다린다.
주어진 조건은 **모두** 맞아야 끝난다. 승인 화면에서는 이동하지 않는다 — 이동하면 걸린 승인이 취소된다.
"""
from __future__ import annotations

import time

from pro_launch.commands.web.frames import frame_scope
from pro_launch.commands.web.session import safe_title
from pro_launch.commands.web.targets import SELECTOR_SYNTAX_HINT, is_selector_syntax_error
from pro_launch.registry import Action

# 조건을 다시 보는 간격(ms)
POLL_INTERVAL_MILLISECONDS = 500
# 기본 대기 상한(초) — 사람이 다른 기기에서 승인하는 시간
DEFAULT_WAIT_SECONDS = 120

# 보이는 글자 전체 (innerText 는 숨긴 글자를 빼고 준다)
VISIBLE_TEXT_JS = "() => document.body ? document.body.innerText : ''"
# --reload-every 하한(초) — 서버를 두드리지 않게 · 새로고침 한 번의 로드 상한(초)
MINIMUM_RELOAD_SECONDS = 5
RELOAD_LOAD_SECONDS = 15


class InvalidSelectorError(Exception):
    """선택자 문법 오류: '아직 안 보임' 이 아니라 즉시 실패할 일"""


def reload_page(page) -> bool:
    """새로고침 한 번. 실패(로드 지연 · 이동 중)해도 다음 바퀴에 다시 본다 > 성공 여부"""
    try:
        page.reload(wait_until="domcontentloaded", timeout=RELOAD_LOAD_SECONDS * 1000)
        return True
    except Exception:
        return False


def wait_conditions(args) -> dict:
    """주어진 조건만 모은다. 이름 → 기대값"""
    named = {"url_contains": args.url_contains, "text": args.text, "gone": args.gone, "selector": args.selector}
    return {name: value for name, value in named.items() if value}


def unmet_conditions(conditions: dict, url: str, visible_text: str, is_selector_visible: bool) -> list[str]:
    """아직 안 맞은 조건 이름들. 빈 목록이면 끝"""
    unmet = []
    if "url_contains" in conditions and conditions["url_contains"] not in url:
        unmet.append("url_contains")
    if "text" in conditions and conditions["text"] not in visible_text:
        unmet.append("text")
    if "gone" in conditions and conditions["gone"] in visible_text:
        unmet.append("gone")
    if "selector" in conditions and not is_selector_visible:
        unmet.append("selector")
    return unmet


def _read_snapshot(page, scope, conditions: dict) -> tuple[str, str, bool]:
    """(주소, 보이는 글자, 선택자가 보이나). 이동 중이라 못 읽으면 빈 값 — 다음 바퀴에 다시 본다"""
    try:
        visible_text = scope.evaluate(VISIBLE_TEXT_JS) if ("text" in conditions or "gone" in conditions) else ""
    except Exception:
        visible_text = ""
    is_selector_visible = False
    if "selector" in conditions:
        try:
            locator = scope.locator(conditions["selector"])
            is_selector_visible = locator.count() > 0 and locator.first.is_visible()
        except Exception as error:
            if is_selector_syntax_error(str(error)):
                raise InvalidSelectorError(str(error)[:200]) from error
            is_selector_visible = False   # 이동 중 문맥 파괴 등 — 다음 바퀴에 다시 본다
    return page.url, visible_text or "", is_selector_visible


def execute(page, args, state: dict) -> dict:
    conditions = wait_conditions(args)
    if not conditions:
        return {"ok": False, "code": "nothing_to_wait_for", "action": "wait",
                "error": "Give at least one of --url-contains · --text · --gone · --selector",
                "next": 'web wait --text "Saved" --timeout 30'}
    scope, failure = frame_scope(page, args, "wait")
    if failure:
        return failure
    reload_seconds = getattr(args, "reload_every", None)
    if reload_seconds is not None and reload_seconds < MINIMUM_RELOAD_SECONDS:
        return {"ok": False, "code": "reload_too_frequent", "action": "wait", "reload_every": reload_seconds,
                "error": f"--reload-every must be at least {MINIMUM_RELOAD_SECONDS}s",
                "next": f"web wait --text <text> --reload-every 15 --timeout {args.timeout}"}
    started = time.monotonic()
    deadline = started + args.timeout
    last_reload = started
    reload_count = 0
    # 마지막 한 번은 시간이 지나도 본다 — 경계에서 맞은 것을 놓치지 않게
    while True:
        try:
            url, visible_text, is_selector_visible = _read_snapshot(page, scope, conditions)
        except InvalidSelectorError as error:
            return {"ok": False, "code": "bad_selector", "action": "wait", "conditions": conditions,
                    "error": f"Selector syntax error: {error}", "hint": SELECTOR_SYNTAX_HINT,
                    "next": "web inspect  # get element candidates and selectors, then fix --selector"}
        unmet = unmet_conditions(conditions, url, visible_text, is_selector_visible)
        waited_seconds = round(time.monotonic() - started, 1)
        if not unmet:
            return {"action": "wait", "conditions": conditions, "waited_seconds": waited_seconds,
                    "reloads": reload_count, "url": url, "title": safe_title(page),
                    "summary": f"Conditions met after {waited_seconds}s", "next": "web text  # read the changed screen"}
        if time.monotonic() >= deadline:
            return {"ok": False, "code": "wait_timeout", "action": "wait", "conditions": conditions,
                    "unmet": unmet, "waited_seconds": waited_seconds, "reloads": reload_count,
                    "url": url, "title": safe_title(page),
                    "error": f"Conditions not met within {args.timeout}s: {', '.join(unmet)}",
                    "next": "web text  # look at the current screen. If it is waiting for approval, do not navigate; call web wait again"}
        page.wait_for_timeout(POLL_INTERVAL_MILLISECONDS)
        # 새로고침해야 바뀌는 화면(PR 상태 · 배포 결과) — 정한 간격마다 다시 받는다 (#930)
        if reload_seconds and time.monotonic() - last_reload >= reload_seconds and time.monotonic() < deadline:
            reload_count += reload_page(page)
            last_reload = time.monotonic()
            if args.frame:
                # 새로고침하면 iframe 문서도 새것이다 — 다시 고른다 (아직 안 그려졌으면 다음 바퀴에)
                scope = frame_scope(page, args, "wait")[0] or scope


def configure(p) -> None:
    p.add_argument("--url-contains", dest="url_contains", default=None, help="Until the URL contains this text")
    p.add_argument("--gone", default=None, help="Until this text disappears from the screen (loading or uploading messages)")
    p.add_argument("--timeout", type=int, default=DEFAULT_WAIT_SECONDS,
                   help=f"Wait limit (seconds, default {DEFAULT_WAIT_SECONDS})")
    p.add_argument("--reload-every", dest="reload_every", type=int, default=None,
                   help=f"Reload every N seconds while waiting (min {MINIMUM_RELOAD_SECONDS}) — for screens that change only on reload")


ACTION = Action(name="wait", run=execute, configure=configure, options=("text", "selector", "frame"),
                help="Wait until the URL, text, gone and element conditions are all met (every condition given)",
                example='web wait --text "Merged" --reload-every 15 --timeout 180')
