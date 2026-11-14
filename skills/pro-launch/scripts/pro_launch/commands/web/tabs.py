"""Per-session tab ownership: named tab records, selection, detecting screens changed by other sessions (#878).

Several agent sessions share one repo's persistent browser. If all drive "the current page" they overwrite each other
(a real incident lost a long unsaved input). Each session drives its own tab via `LAUNCH_TAB=<name>`.

Tabs are identified by CDP targetId — it stays the same while the tab lives, even though each call reattaches and gets a new Playwright Page.
State file (browser.json):
    tabs:      {name: {"target_id": ..., "created_at": ...}}
    tab_marks: {"<tab>@<session>": {"target_id": ..., "url": ...}}   # state when that session's last command finished

Sessions are told apart by LAUNCH_SESSION > CLAUDE_CODE_SESSION_ID. With neither, all sessions on the same tab share one record.
"""
from __future__ import annotations

import os
import time
from urllib.parse import urlsplit

# Session-splitting source of truth is runtime (shared with device ownership) — re-exported here
from pro_launch.runtime.session_identity import ANONYMOUS_SESSION, SESSION_ENV_VARS, session_identity  # noqa: F401

# Environment variable holding the tab name a session drives
TAB_ENV_VAR = "LAUNCH_TAB"
DEFAULT_TAB_KEY = "default"
# Guide tabs Chrome opens on its own. Not working tabs
BROWSER_INTERNAL_PREFIXES = ("chrome://", "chrome-untrusted://", "devtools://", "edge://")


def session_tab_name() -> str | None:
    name = (os.environ.get(TAB_ENV_VAR) or "").strip()
    return name or None


def mark_key(tab_name: str | None = None) -> str:
    """Record key for this session and tab — if another session moves the same tab, it diverges from my record and shows up."""
    return f"{tab_name or session_tab_name() or DEFAULT_TAB_KEY}@{session_identity()}"


def tab_of_mark_key(key: str) -> str:
    return key.rsplit("@", 1)[0]


# Other sessions that moved within this window count as still in use (6 hours, same as the browser-abandon check, #1094)
OTHER_SESSION_ACTIVE_SECONDS = 6 * 3600
# Retry count and interval while waiting for a new tab to appear in Playwright (about 3 seconds)
BACKGROUND_TAB_WAIT_TRIES = 30
BACKGROUND_TAB_WAIT_MILLISECONDS = 100

# New tabs this session already reported: {"<tab>@<session>": [targetId, ...]}
REPORTED_POPUPS_KEY = "reported_popups"


def target_info(page) -> dict | None:
    """CDP targetInfo of a tab (targetId, openerId, url). None if unreadable (fake page, non-CDP connection)."""
    try:
        cdp = page.context.new_cdp_session(page)
        try:
            return cdp.send("Target.getTargetInfo")["targetInfo"]
        finally:
            cdp.detach()
    except Exception:
        return None


def target_id(page) -> str | None:
    info = target_info(page)
    return info.get("targetId") if info else None


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


def last_used_tab_page(ctx, state: dict):
    """Tab this session drove last (None if another session took it by name)
    Tab order changes on every attach > picking "the last tab" flips between popup and original tab (#987)"""
    mark = (state.get("tab_marks") or {}).get(mark_key()) or {}
    owned_target_ids = {entry.get("target_id") for entry in (state.get("tabs") or {}).values()}
    if not mark.get("target_id") or mark["target_id"] in owned_target_ids:
        return None
    return find_page_by_target(ctx, mark["target_id"])


def opened_tabs(page, state: dict) -> list[dict]:
    """New tabs (openerId) this tab opened that this session has not reported > [{target_id, url, title}] (#987)
    Checked at the end of every command > windows that open a few seconds late are caught by the next command"""
    opener_target_id = target_id(page)
    if not opener_target_id:
        return []
    reported = set((state.get(REPORTED_POPUPS_KEY) or {}).get(mark_key()) or [])
    found = []
    for candidate in usable_pages(page.context):
        info = target_info(candidate) or {}
        if info.get("openerId") != opener_target_id or info.get("targetId") in reported:
            continue
        found.append({"target_id": info["targetId"], "url": candidate.url,
                      "title": (info.get("title") or "")[:120]})
    if found:
        reported |= {tab["target_id"] for tab in found}
        state.setdefault(REPORTED_POPUPS_KEY, {})[mark_key()] = sorted(reported)
    return found


def default_tab_page(ctx, state: dict):
    """Tab for an unnamed session: the last tab, skipping tabs other sessions took by name. Opens a new one if none."""
    owned_target_ids = {entry.get("target_id") for entry in (state.get("tabs") or {}).values()}
    candidates = usable_pages(ctx)
    if owned_target_ids:
        candidates = [p for p in candidates if target_id(p) not in owned_target_ids]
    return candidates[-1] if candidates else ctx.new_page()


def new_tab_page(ctx, is_front: bool = False):
    """Open a new tab. Background by default — new_page brings the tab to the front and changes the tab a person was viewing (#1094).
    If the connection can't open in the background, fall back to new_page."""
    if is_front:
        page = ctx.new_page()
        page.bring_to_front()
        return page
    try:
        session = ctx.browser.new_browser_cdp_session()
        try:
            created_target_id = session.send("Target.createTarget", {"url": "about:blank", "background": True})["targetId"]
        finally:
            session.detach()
    except Exception:
        return ctx.new_page()
    anchor = usable_pages(ctx)[0]
    for _ in range(BACKGROUND_TAB_WAIT_TRIES):
        page = find_page_by_target(ctx, created_target_id)
        if page is not None:
            return page
        anchor.wait_for_timeout(BACKGROUND_TAB_WAIT_MILLISECONDS)
    return ctx.new_page()


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
    """Part that identifies the same screen (scheme, host, path). Query and hash change within the same screen."""
    parts = urlsplit(url or "")
    return parts.scheme, parts.netloc, parts.path.rstrip("/")


def read_time_origin(page) -> float | None:
    """When the document was created — changes on reload. None if unreadable (navigating)"""
    try:
        return page.evaluate("performance.timeOrigin")
    except Exception:
        return None


def tab_mark(page) -> dict:
    """Current state of this tab: which tab, which screen, which document, when"""
    return {"target_id": target_id(page), "url": page.url, "time_origin": read_time_origin(page), "at": int(time.time())}


def active_other_sessions(state: dict) -> list[dict]:
    """Tabs of other sessions that used this browser recently > [{tab, url, target_id, idle_minutes}]. Empty if sessions can't be told apart.
    Old records (no at) count as in use — overwriting someone else's tab is worse."""
    me = session_identity()
    if me == ANONYMOUS_SESSION:
        return []
    now, found = time.time(), []
    for key, mark in (state.get("tab_marks") or {}).items():
        last_seen = mark.get("at")
        if key.endswith(f"@{me}") or (last_seen and now - last_seen > OTHER_SESSION_ACTIVE_SECONDS):
            continue
        found.append({"tab": tab_of_mark_key(key), "url": mark.get("url"), "target_id": mark.get("target_id"),
                      "idle_minutes": round((now - last_seen) / 60) if last_seen else None})
    return found


def is_other_session_tab(page, state: dict) -> bool:
    """Is this a tab another session uses that this session never drove"""
    if (state.get("tab_marks") or {}).get(mark_key()):
        return False
    current_target_id = target_id(page)
    return any(entry["target_id"] == current_target_id for entry in active_other_sessions(state))


def reload_notice(page, state: dict) -> dict | None:
    """Was the same screen reloaded after this session's last command (#1094).
    A reload clears refs, half-typed text and open menus — ref_stale alone doesn't reveal the cause."""
    mark = (state.get("tab_marks") or {}).get(mark_key()) or {}
    previous_origin = mark.get("time_origin")
    current_origin = read_time_origin(page)
    if previous_origin is None or current_origin is None or current_origin == previous_origin:
        return None
    if _page_identity(mark.get("url")) != _page_identity(page.url):
        return None  # a different screen is reported by drift_warning
    return {"code": "page_reloaded", "seconds_ago": round(time.time() - current_origin / 1000, 1),
            "hint": "The page reloaded between commands, and this session did not ask for it. Refs, typed text and open menus "
                    "are gone. Pick again with web find, and do steps that depend on each other in one web script"}


def attach_reload_notice(payload: dict, notice: dict) -> None:
    """Report in the result that the page reloaded between commands. Appended to the summary/error text so it survives --brief"""
    payload["page_reloaded"] = notice
    sentence = f"The page reloaded by itself {notice['seconds_ago']:g}s ago, so earlier refs and typed text are gone"
    key = "error" if payload.get("ok") is False and payload.get("error") else "summary"
    payload[key] = f"{payload[key]} — {sentence}" if payload.get(key) else sentence


def drift_warning(page, state: dict) -> dict | None:
    """Did the tab change after this session's last command (switched to another tab, navigated to another screen). Warning dict if so."""
    key = mark_key()
    mark = (state.get("tab_marks") or {}).get(key)
    if not mark:
        if not is_other_session_tab(page, state):
            return None
        return {"code": "tab_used_by_other_session", "tab": tab_of_mark_key(key), "current_url": page.url,
                "hint": ("Another session is working in this tab. Do not change it: "
                         f"run web tab new --name <name> and prefix commands with {TAB_ENV_VAR}=<name>")}
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
    """Record this session's tab state after the command — so the next command can tell another session's navigation or a reload."""
    try:
        mark = tab_mark(page)
    except Exception:
        return
    state.setdefault("tab_marks", {})[mark_key()] = mark


def tabs_summary(ctx, page, state: dict, acting_name: str | None = None) -> dict:
    """How many tabs there are and which tab this command ran in."""
    pages = usable_pages(ctx)
    name_by_target_id = {entry.get("target_id"): name for name, entry in (state.get("tabs") or {}).items()}
    acting_index = next((i for i, p in enumerate(pages) if p is page), None)
    return {"count": len(pages), "acting_on": acting_name or session_tab_name() or DEFAULT_TAB_KEY,
            "acting_index": acting_index,
            "named": sorted(name for tid, name in name_by_target_id.items() if tid)}
