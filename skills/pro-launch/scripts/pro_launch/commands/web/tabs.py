"""세션별 탭 소유권: 이름 붙은 탭 기록 · 고르기 · 다른 세션이 바꾼 화면 감지 (#878).

같은 레포의 영속 브라우저를 여러 agent 세션이 함께 쓴다. 모두 "지금 페이지" 를 몰면 서로 덮어쓴다
(저장 안 한 긴 입력이 날아간 실사고). 세션마다 `LAUNCH_TAB=<이름>` 으로 자기 탭을 몰게 한다.

탭은 CDP targetId 로 알아본다 — 매 호출 새로 붙어 Playwright Page 객체가 바뀌어도 탭이 살아 있는 동안 같다.
상태 파일(browser.json):
    tabs:      {이름: {"target_id": ..., "created_at": ...}}
    tab_marks: {"<탭>@<세션>": {"target_id": ..., "url": ...}}   # 그 세션의 마지막 명령이 끝난 모습

세션은 LAUNCH_SESSION > CLAUDE_CODE_SESSION_ID 로 가른다. 둘 다 없으면 같은 탭의 모든 세션이 기록 하나를 함께 쓴다.
"""
from __future__ import annotations

import os
import time
from urllib.parse import urlsplit

# 세션 가르기 원본은 runtime (기기 소유와 공용) — 여기서는 재노출
from pro_launch.runtime.session_identity import ANONYMOUS_SESSION, SESSION_ENV_VARS, session_identity  # noqa: F401

# 세션이 몰 탭 이름을 담는 환경변수
TAB_ENV_VAR = "LAUNCH_TAB"
DEFAULT_TAB_KEY = "default"
# Chrome 이 스스로 띄우는 안내 탭. 작업 탭이 아니다
BROWSER_INTERNAL_PREFIXES = ("chrome://", "chrome-untrusted://", "devtools://", "edge://")


def session_tab_name() -> str | None:
    name = (os.environ.get(TAB_ENV_VAR) or "").strip()
    return name or None


def mark_key(tab_name: str | None = None) -> str:
    """이 세션 · 이 탭의 기록 키 — 다른 세션이 같은 탭을 움직이면 내 기록과 어긋나 드러난다."""
    return f"{tab_name or session_tab_name() or DEFAULT_TAB_KEY}@{session_identity()}"


def tab_of_mark_key(key: str) -> str:
    return key.rsplit("@", 1)[0]


def target_id(page) -> str | None:
    """탭의 CDP targetId. 못 읽으면 None (가짜 페이지 · CDP 아닌 연결)."""
    try:
        cdp = page.context.new_cdp_session(page)
        try:
            return cdp.send("Target.getTargetInfo")["targetInfo"]["targetId"]
        finally:
            cdp.detach()
    except Exception:
        return None


def usable_pages(ctx) -> list:
    live = [p for p in ctx.pages if not p.is_closed()]
    return [p for p in live if not p.url.startswith(BROWSER_INTERNAL_PREFIXES)]


def find_page_by_target(ctx, wanted_target_id: str | None):
    if not wanted_target_id:
        return None
    for page in usable_pages(ctx):
        if target_id(page) == wanted_target_id:
            return page
    return None


def named_tab_page(ctx, state: dict, name: str):
    entry = (state.get("tabs") or {}).get(name) or {}
    return find_page_by_target(ctx, entry.get("target_id"))


def default_tab_page(ctx, state: dict):
    """이름 없는 세션의 탭: 다른 세션이 이름 붙여 가져간 탭은 건너뛴 마지막 탭. 없으면 새로 연다."""
    owned_target_ids = {entry.get("target_id") for entry in (state.get("tabs") or {}).values()}
    candidates = usable_pages(ctx)
    if owned_target_ids:
        candidates = [p for p in candidates if target_id(p) not in owned_target_ids]
    return candidates[-1] if candidates else ctx.new_page()


def register_tab(state: dict, name: str, page) -> dict:
    entry = {"target_id": target_id(page), "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    state.setdefault("tabs", {})[name] = entry
    return entry


def forget_tab(state: dict, name: str) -> None:
    (state.get("tabs") or {}).pop(name, None)
    marks = state.get("tab_marks") or {}
    for key in [k for k in marks if tab_of_mark_key(k) == name]:
        marks.pop(key, None)


def _page_identity(url: str | None) -> tuple[str, str, str]:
    """같은 화면인지 볼 부분 (scheme·host·path). 쿼리·해시는 같은 화면 안에서도 바뀐다."""
    parts = urlsplit(url or "")
    return parts.scheme, parts.netloc, parts.path.rstrip("/")


def drift_warning(page, state: dict) -> dict | None:
    """이 세션의 마지막 명령 뒤에 탭이 바뀌었나 (다른 탭으로 바뀜 · 다른 화면으로 이동). 바뀌었으면 경고 dict."""
    key = mark_key()
    mark = (state.get("tab_marks") or {}).get(key)
    if not mark:
        return None
    try:
        current_url = page.url
    except Exception:
        return None
    current_target_id = target_id(page)
    is_other_tab = bool(mark.get("target_id") and current_target_id and mark["target_id"] != current_target_id)
    is_moved = _page_identity(mark.get("url")) != _page_identity(current_url)
    if not (is_other_tab or is_moved):
        return None
    return {"code": "page_changed_by_other_session", "tab": tab_of_mark_key(key),
            "previous_url": mark.get("url"), "current_url": current_url,
            "hint": ("The screen changed although this session did not navigate — another session is using the same tab. "
                     f"Run web tab new --name <name>, then work in your own tab with {TAB_ENV_VAR}=<name>")}


def mark_tab(page, state: dict) -> None:
    """명령이 끝난 뒤 이 세션 탭의 모습을 적는다 — 다음 명령에서 다른 세션의 이동을 가른다."""
    try:
        url = page.url
    except Exception:
        return
    state.setdefault("tab_marks", {})[mark_key()] = {"target_id": target_id(page), "url": url}


def tabs_summary(ctx, page, state: dict, acting_name: str | None = None) -> dict:
    """탭이 몇 개고 이번 명령이 어느 탭에서 돌았나."""
    pages = usable_pages(ctx)
    name_by_target_id = {entry.get("target_id"): name for name, entry in (state.get("tabs") or {}).items()}
    acting_index = next((i for i, p in enumerate(pages) if p is page), None)
    return {"count": len(pages), "acting_on": acting_name or session_tab_name() or DEFAULT_TAB_KEY,
            "acting_index": acting_index,
            "named": sorted(name for tid, name in name_by_target_id.items() if tid)}
