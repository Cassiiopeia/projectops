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
                "error": "--url-contains · --text · --gone · --selector 중 하나는 있어야 합니다",
                "next": 'web wait --text "저장됨" --timeout 30'}
    scope, failure = frame_scope(page, args, "wait")
    if failure:
        return failure
    reload_seconds = getattr(args, "reload_every", None)
    if reload_seconds is not None and reload_seconds < MINIMUM_RELOAD_SECONDS:
        return {"ok": False, "code": "reload_too_frequent", "action": "wait", "reload_every": reload_seconds,
                "error": f"--reload-every 는 {MINIMUM_RELOAD_SECONDS}초 이상이어야 합니다",
                "next": f"web wait --text <글자> --reload-every 15 --timeout {args.timeout}"}
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
                    "error": f"선택자 문법 오류: {error}", "hint": SELECTOR_SYNTAX_HINT,
                    "next": "web inspect  # 요소 후보와 선택자를 받아 --selector 를 고친다"}
        unmet = unmet_conditions(conditions, url, visible_text, is_selector_visible)
        waited_seconds = round(time.monotonic() - started, 1)
        if not unmet:
            return {"action": "wait", "conditions": conditions, "waited_seconds": waited_seconds,
                    "reloads": reload_count, "url": url, "title": safe_title(page),
                    "summary": f"{waited_seconds}초 만에 조건이 맞았다", "next": "web text  # 바뀐 화면을 읽는다"}
        if time.monotonic() >= deadline:
            return {"ok": False, "code": "wait_timeout", "action": "wait", "conditions": conditions,
                    "unmet": unmet, "waited_seconds": waited_seconds, "reloads": reload_count,
                    "url": url, "title": safe_title(page),
                    "error": f"{args.timeout}초 안에 조건이 맞지 않았습니다: {', '.join(unmet)}",
                    "next": "web text  # 지금 화면을 본다. 승인 대기 화면이면 이동하지 말고 web wait 를 다시 부른다"}
        page.wait_for_timeout(POLL_INTERVAL_MILLISECONDS)
        # 새로고침해야 바뀌는 화면(PR 상태 · 배포 결과) — 정한 간격마다 다시 받는다 (#930)
        if reload_seconds and time.monotonic() - last_reload >= reload_seconds and time.monotonic() < deadline:
            reload_count += reload_page(page)
            last_reload = time.monotonic()
            if args.frame:
                # 새로고침하면 iframe 문서도 새것이다 — 다시 고른다 (아직 안 그려졌으면 다음 바퀴에)
                scope = frame_scope(page, args, "wait")[0] or scope


def configure(p) -> None:
    p.add_argument("--url-contains", dest="url_contains", default=None, help="주소에 이 글자가 들어올 때까지")
    p.add_argument("--gone", default=None, help="이 글자가 화면에서 사라질 때까지 (로딩·업로드 중 문구)")
    p.add_argument("--timeout", type=int, default=DEFAULT_WAIT_SECONDS,
                   help=f"대기 상한(초, 기본 {DEFAULT_WAIT_SECONDS})")
    p.add_argument("--reload-every", dest="reload_every", type=int, default=None,
                   help=f"이 초마다 새로고침하며 기다린다 (최소 {MINIMUM_RELOAD_SECONDS}) — 새로고침해야 바뀌는 화면")


ACTION = Action(name="wait", run=execute, configure=configure, options=("text", "selector", "frame"),
                help="주소·글자·사라짐·요소 조건이 맞을 때까지 기다린다 (주어진 조건 모두)",
                example='web wait --text "Merged" --reload-every 15 --timeout 180')
