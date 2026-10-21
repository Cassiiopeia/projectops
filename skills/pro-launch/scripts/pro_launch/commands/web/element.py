"""조작할 요소 하나를 고른다 — click · type · select · check · press · hover · download 가 함께 쓴다.

순서: 대상 확인(--ref · --selector) > 찾기(못 찾으면 후보) > 비활성이면 바로 실패(#888) > 읽기 전용 세션 막기
조작 자체가 시간 초과면 perform_on_target 이 후보를 담은 element_not_actionable 로 바꾼다 (#888)
"""
from __future__ import annotations

from pro_launch.commands.web.candidates import attach_candidates
from pro_launch.commands.web.frames import frame_scope
from pro_launch.commands.web.targets import REF_ATTR, is_mutating_target

# 대상 요소를 기다리는 기본 시간(초) — 추측이 빗나가면 이만큼만 쓴다 (#888, 이전 10)
TARGET_WAIT_SECONDS = 4
# 누른 뒤 결과(--expect-* · 내려받기 시작 · 로딩)를 기다리는 기본 시간(초)
OUTCOME_WAIT_SECONDS = 10


# 요소 설명 + 보이는가 · 비활성인가 (비밀번호 칸의 값은 싣지 않는다). 비활성은 disabled 속성 · aria-disabled · 비활성 fieldset 안 셋 다 본다
DESCRIBE_STATE_JS = """(e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
  return { tag: e.tagName.toLowerCase(), role: e.getAttribute('role'), type: e.getAttribute('type'),
    text: (e.type === 'password' ? '' : (e.innerText || e.value || '')).replace(/\\s+/g, ' ').trim().slice(0, 120),
    aria: e.getAttribute('aria-label') || e.getAttribute('title'), href: e.getAttribute('href'),
    name: e.getAttribute('name'), aria_label: e.getAttribute('aria-label'), placeholder: e.getAttribute('placeholder'),
    visible: r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none',
    disabled: !!e.disabled || e.getAttribute('aria-disabled') === 'true' || !!e.closest('fieldset[disabled]') }; }"""


def target_wait_seconds(args) -> int:
    """대상 요소를 기다리는 시간. --timeout 을 주면 그 값"""
    timeout = getattr(args, "timeout", None)
    return TARGET_WAIT_SECONDS if timeout is None else timeout


def outcome_wait_seconds(args) -> int:
    """누른 뒤 결과를 기다리는 시간. --timeout 을 주면 그 값"""
    timeout = getattr(args, "timeout", None)
    return OUTCOME_WAIT_SECONDS if timeout is None else timeout


def target_selector(args) -> str | None:
    """--ref 가 있으면 그 번호의 요소, 아니면 --selector."""
    if getattr(args, "ref", None) is not None:
        return f'[{REF_ATTR}="{args.ref}"]'
    return getattr(args, "selector", None)


def target_label(info: dict) -> str:
    return (info.get("text") or info.get("aria") or info.get("tag") or "")[:40]


def locate_target(page, args, state: dict, action: str, *, should_wait: bool = False,
                  should_guard_mutating: bool = True):
    """(요소, 설명, 실패 결과). 실패 결과가 있으면 요소는 None 이다.

    should_wait: 선택자가 아직 없으면 대상 대기 시간까지 붙기를 기다린다 (입력창이 늦게 그려지는 화면).
    ref 는 기다리지 않는다 — 없으면 화면이 바뀐 것이라 다시 골라야 한다.
    """
    selector = target_selector(args)
    if not selector:
        return None, None, {"ok": False, "code": "target_required", "action": action,
                            "error": "--ref or --selector is required",
                            "next": "web inspect  # get numbered input and button candidates, then pick one with --ref"}
    # --frame 이면 그 iframe 안에서만 찾는다 (#877). 후보도 그 안에서 고른다
    scope, failure = frame_scope(page, args, action)
    if failure:
        return None, None, failure
    locator = scope.locator(selector)
    if locator.count() == 0 and should_wait and args.ref is None:
        try:
            locator.first.wait_for(state="attached", timeout=target_wait_seconds(args) * 1000)
        except Exception:
            pass  # 시간 안에 안 붙으면 아래 count() == 0 경로가 실패를 알린다
    if locator.count() == 0:
        if args.ref is not None:
            return None, None, attach_candidates(
                {"ok": False, "code": "ref_stale", "action": action, "url": page.url,
                 "error": f"ref {args.ref} is not on the screen (gone after navigation or re-render)",
                 "next": "web find  # pick again from the current screen"}, scope, None, action)
        return None, None, attach_candidates(
            {"ok": False, "code": "selector_not_found", "action": action, "url": page.url,
             "error": f"No element matches {args.selector}", "next": "web find --text <text>"},
            scope, args.selector, action)
    element = locator.first
    info = element.evaluate(DESCRIBE_STATE_JS)
    # 실제로 고른 요소와 맞은 개수 — 쉼표 선택자가 엉뚱한 첫 요소에 들어가도 ok 가 나던 것을 드러낸다 (#931)
    info["matches"] = locator.count()
    if args.ref is not None:
        info["ref"] = args.ref
    if getattr(args, "frame", None):
        info["frame"] = args.frame
    # 보이는데 비활성이면 타임아웃까지 기다려도 소용없다 — 바로 알린다 (#888)
    if info.get("visible") and info.get("disabled"):
        return None, info, {"ok": False, "code": "element_disabled", "action": action, "target": info,
                            "url": page.url,
                            "error": f"'{target_label(info)}' is disabled",
                            "next": "web inspect  # check for inputs or checkboxes that must be filled first"}
    if (should_guard_mutating and state.get("readonly") and is_mutating_target(info)
            and not getattr(args, "confirm_mutating", False)):
        return None, info, {"ok": False, "code": "mutating_blocked", "action": action, "clicked": None,
                            "target": info, "url": page.url,
                            "error": f"Read-only session: did not touch '{target_label(info)}'",
                            "next": "If it really must be done, tell the user what will change, get approval, then add --confirm-mutating"}
    return element, info, None


def is_timeout_error(error: Exception) -> bool:
    """Playwright 대기 시간 초과인가 (TimeoutError 또는 'Timeout …ms exceeded')."""
    return "Timeout" in type(error).__name__ or "timeout" in str(error).lower()


def not_actionable_failure(page, args, action: str, info: dict | None, error: Exception) -> dict:
    """요소는 있는데 대기 시간 안에 조작할 수 없었다 (숨김·가려짐·움직임) — 후보를 싣는다."""
    # Playwright 문구의 첫 줄만 — 뒤따르는 호출 기록에 입력값(비밀번호)이 섞일 수 있다
    detail = str(error).strip().splitlines()[0][:200] if str(error).strip() else type(error).__name__
    is_secret_input = bool(getattr(args, "text_env", None) or getattr(args, "cred", None))
    if is_secret_input and getattr(args, "text", None):
        detail = detail.replace(args.text, "***")
    label = target_label(info or {}) or (getattr(args, "selector", None) or "")
    failure = {"ok": False, "code": "element_not_actionable", "action": action, "target": info, "url": page.url,
               "error": f"Could not act on '{label}' within {target_wait_seconds(args)}s (hidden, covered or moving)",
               "detail": detail, "next": "web inspect  # pick a visible input or button again by ref"}
    selector = None if getattr(args, "ref", None) is not None else getattr(args, "selector", None)
    scope = frame_scope(page, args, action)[0] or page
    return attach_candidates(failure, scope, selector, action)


def perform_on_target(page, args, action: str, info: dict | None, operation) -> dict | None:
    """조작 하나를 한다. 대기 시간 초과면 후보를 담은 실패 결과를, 성공이면 None. 그 밖의 예외는 그대로 올린다."""
    try:
        operation()
    except Exception as error:
        if not is_timeout_error(error):
            raise
        return not_actionable_failure(page, args, action, info, error)
    return None


def attach_match_warning(payload: dict) -> None:
    """조작 결과의 대상이 선택자 여러 개에 맞았으면 최상위에 matches · warning 을 싣는다 (ref 는 하나라 해당 없음)"""
    for key in ("target", "clicked"):
        info = payload.get(key)
        if isinstance(info, dict) and (info.get("matches") or 0) > 1 and "ref" not in info:
            payload["matches"] = info["matches"]
            payload.setdefault("warning", "multiple_matches")
            payload.setdefault("warning_detail", (
                f"Selector matched {info['matches']} elements and used the first ({info.get('tag')} "
                f"'{target_label(info)}') — if that is not the intended element, pick one with --ref from web find or web inspect"))
            return
