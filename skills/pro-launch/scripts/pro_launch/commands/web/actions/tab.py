"""`web tab new|list|use|close` — 세션마다 자기 탭에서 일한다 (#878).

`web tab new --name A` 후 `LAUNCH_TAB=A` 를 붙여 부르면 그 세션의 web 명령은 A 탭만 몬다.
다른 세션이 이름 붙인 탭은 닫지 않는다 — 자기 이름을 줘야 닫는다.
"""
from __future__ import annotations

import time
from pathlib import Path

from pro_launch.commands.web import tabs
from pro_launch.commands.web.session import read_url_title, web_connect
from pro_launch.registry import Action
from pro_launch.runtime.browser import read_state, write_state
from pro_launch.runtime.output import out

TAB_COMMANDS = ("new", "list", "use", "close")


def _tab_list(ctx, state: dict) -> dict:
    name_by_target_id = {entry.get("target_id"): name for name, entry in (state.get("tabs") or {}).items()}
    rows = []
    for index, page in enumerate(tabs.usable_pages(ctx)):
        url, title = read_url_title(page, timeout=2)
        rows.append({"index": index, "name": name_by_target_id.get(tabs.target_id(page)),
                     "url": url, "title": title})
    live_names = {row["name"] for row in rows if row["name"]}
    # 닫힌 탭의 이름은 지운다 — 같은 이름으로 다시 만들 수 있게
    for name in list(state.get("tabs") or {}):
        if name not in live_names:
            tabs.forget_tab(state, name)
    return {"action": "tab", "tab_command": "list", "tabs": rows, "count": len(rows),
            "session_tab": tabs.session_tab_name(),
            "summary": f"탭 {len(rows)}개 (이름 붙은 것 {len(live_names)}개)",
            "next": f"web tab new --name <이름>  # 그 뒤 {tabs.TAB_ENV_VAR}=<이름> 으로 부른다"}


def _tab_new(ctx, args, state: dict) -> dict:
    name = args.name or f"tab-{time.strftime('%H%M%S')}"
    if tabs.named_tab_page(ctx, state, name) is not None:
        return {"ok": False, "code": "tab_name_taken", "error": f"'{name}' 탭이 이미 있습니다",
                "next": f"{tabs.TAB_ENV_VAR}={name} launch_cli.py web text  # 그 탭을 쓰거나 다른 이름을 준다"}
    page = ctx.new_page()
    tabs.register_tab(state, name, page)
    if args.url:
        page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
    url, title = read_url_title(page)
    state.setdefault("tab_marks", {})[tabs.mark_key(name)] = {"target_id": tabs.target_id(page), "url": url}
    return {"action": "tab", "tab_command": "new", "name": name, "url": url, "title": title,
            "summary": f"'{name}' 탭을 만들었습니다",
            "next": f"{tabs.TAB_ENV_VAR}={name} launch_cli.py web text  # 이 세션의 모든 web 명령 앞에 붙인다"}


def _tab_use(ctx, args, state: dict) -> dict:
    """이름이 있으면 확인, --index 를 주면 이름 없는 기존 탭에 이름을 붙인다."""
    if args.index is not None:
        pages = tabs.usable_pages(ctx)
        if not 0 <= args.index < len(pages):
            return {"ok": False, "code": "tab_not_found", "error": f"{args.index}번 탭이 없습니다",
                    "next": "web tab list"}
        page = pages[args.index]
        owned = {e.get("target_id") for e in (state.get("tabs") or {}).values()}
        if tabs.target_id(page) in owned:
            return {"ok": False, "code": "tab_owned", "error": f"{args.index}번 탭은 이미 다른 이름이 붙어 있습니다",
                    "next": "web tab list"}
        tabs.register_tab(state, args.name, page)
    elif tabs.named_tab_page(ctx, state, args.name) is None:
        return {"ok": False, "code": "tab_not_found", "error": f"'{args.name}' 탭이 없습니다",
                "next": f"web tab new --name {args.name}"}
    return {"action": "tab", "tab_command": "use", "name": args.name,
            "summary": f"'{args.name}' 탭을 쓸 수 있습니다",
            "next": f"{tabs.TAB_ENV_VAR}={args.name} launch_cli.py web text"}


def _tab_close(ctx, args, state: dict) -> dict:
    page = tabs.named_tab_page(ctx, state, args.name)
    tabs.forget_tab(state, args.name)
    if page is None:
        return {"action": "tab", "tab_command": "close", "name": args.name, "already_closed": True,
                "summary": f"'{args.name}' 탭은 이미 없습니다", "next": None}
    page.close()
    return {"action": "tab", "tab_command": "close", "name": args.name,
            "summary": f"'{args.name}' 탭을 닫았습니다", "next": None}


def execute(args, state: dict, state_f: Path) -> int:
    if args.tab_command in ("use", "close") and not args.name:
        return out({"ok": False, "code": "bad_args", "error": f"web tab {args.tab_command} 은 --name 이 필요합니다",
                    "next": "web tab list"})
    conn, err = web_connect(state, allow_missing_tab=True)
    if err:
        return out(err)
    pw, _browser, page = conn
    tab_names_before = set(state.get("tabs") or {})
    try:
        ctx = page.context
        handlers = {"list": lambda: _tab_list(ctx, state), "new": lambda: _tab_new(ctx, args, state),
                    "use": lambda: _tab_use(ctx, args, state), "close": lambda: _tab_close(ctx, args, state)}
        payload = handlers[args.tab_command]()
    except Exception as e:
        payload = {"ok": False, "code": "web_action_failed", "action": "tab", "error": str(e)[:400],
                   "next": "web tab list"}
    finally:
        pw.stop()
    _save_tab_records(state_f, state, tab_names_before)
    return out(payload)


def _save_tab_records(state_f: Path, state: dict, tab_names_before: set) -> None:
    """이번 호출이 더하고 지운 탭 기록만 지금 파일에 합친다 — 다른 세션이 그사이 쓴 값을 덮지 않게."""
    fresh = read_state(state_f) if state_f.is_file() else state
    current_tabs = state.get("tabs") or {}
    merged_tabs = dict(fresh.get("tabs") or {})
    for name in tab_names_before - set(current_tabs):
        merged_tabs.pop(name, None)
    merged_tabs.update(current_tabs)
    fresh["tabs"] = merged_tabs
    fresh["tab_marks"] = {**(fresh.get("tab_marks") or {}), **(state.get("tab_marks") or {})}
    for key in list(fresh["tab_marks"]):
        if tabs.tab_of_mark_key(key) not in set(fresh["tabs"]) | {tabs.DEFAULT_TAB_KEY}:
            fresh["tab_marks"].pop(key, None)
    write_state(state_f, fresh)


def configure(p) -> None:
    p.add_argument("tab_command", choices=TAB_COMMANDS, help="new 만들기 · list 목록 · use 확인/이름 붙이기 · close 닫기")
    p.add_argument("--name", default=None, help="탭 이름 (LAUNCH_TAB 에 넣는 값)")
    p.add_argument("--index", type=int, default=None, help="use: 이름 없는 기존 탭 번호 (web tab list 의 index)")


ACTION = Action(name="tab", needs="state_online", run=execute, configure=configure, options=("url", "timeout"),
                help="세션 전용 탭을 만들고·보고·닫는다 (LAUNCH_TAB=<이름> 으로 그 탭만 몬다)",
                example="web tab new --name edit-form --url http://localhost:3000/form")
