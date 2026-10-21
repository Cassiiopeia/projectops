"""`web profile` — 브라우저 프로필 보기 · 고르기 · 공들인 상태(로그인) 기록 (#956).

list: 레포 프로필 + 이 컴퓨터 공용 프로필, 각 mark 와 떠 있는 브라우저 · use: 이 레포가 쓸 프로필 기억
mark · unmark: 지금 프로필(또는 --profile)에 로그인 같은 상태를 기록 — tidy 가 그 프로필을 지우지 않고, open --need 가 고른다.
"""
from __future__ import annotations

from pro_launch.registry import Action
from pro_launch.runtime import browser_profiles, device_ledger, device_marks
from pro_launch.runtime.browser import read_state
from pro_launch.runtime.context import project_root
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import pid_alive

PROFILE_OPERATIONS = ("list", "use", "mark", "unmark")


def _profile_row(root, name: str, devices: dict) -> dict:
    """프로필 하나 요약: 이름 · mark · 떠 있는 브라우저 pid."""
    is_repo = name == browser_profiles.REPO_PROFILE_NAME
    key = browser_profiles.profile_mark_key(root, name)
    state_file = (browser_profiles.state_path(root) if is_repo
                  else browser_profiles.shared_profiles_root() / name / browser_profiles.WEB_STATE_FILE_NAME)
    state = read_state(state_file) if state_file.is_file() else {}
    pid = state.get("pid")
    return {"name": name, "key": key, "marks": device_marks.mark_views(devices.get(key) or {}),
            "browser_pid": pid if pid and pid_alive(int(pid)) else None}


def _web_profile(args) -> int:
    root = project_root(args)
    operation = args.operation
    if operation == "list":
        devices = device_ledger.read_ledger()["devices"]
        names = [browser_profiles.REPO_PROFILE_NAME, *browser_profiles.shared_profile_names()]
        current = browser_profiles.chosen_profile(root) or browser_profiles.REPO_PROFILE_NAME
        return out({"action": "profile", "operation": "list", "current": current,
                    "profiles": [_profile_row(root, name, devices) for name in names],
                    "summary": f"Current profile {current} · {len(names) - 1} shared profiles",
                    "next": "web open --profile <name> reuses the same login across repos"})
    if operation == "use":
        name = args.profile or browser_profiles.REPO_PROFILE_NAME
        if name != browser_profiles.REPO_PROFILE_NAME and not browser_profiles.is_valid_profile_name(name):
            return out({"ok": False, "code": "bad_args", "error": f"Profile names use letters, digits and ._- (40 chars max): {name}"})
        browser_profiles.choose_profile(root, name)
        return out({"action": "profile", "operation": "use", "current": name,
                    "summary": f"This repo now uses the {name} profile", "next": "web open"})
    if not args.kind or not args.mark_name:
        return out({"ok": False, "code": "args_required", "error": "--kind and --name are required",
                    "next": "web profile mark --kind login --name google --note 'work account'"})
    key = browser_profiles.profile_mark_key(root, args.profile)
    if operation == "mark":
        mark = device_marks.add_mark(key, args.kind, args.mark_name, args.note)
        return out({"action": "profile", "operation": "mark", "key": key, "mark": mark,
                    "summary": f"Recorded {args.kind}:{args.mark_name} on {key} — protected from cleanup and picked by open --need",
                    "next": f"In another repo: web open --need {args.kind}:{args.mark_name}"})
    is_removed = device_marks.remove_mark(key, args.kind, args.mark_name)
    return out({"action": "profile", "operation": "unmark", "key": key, "removed": is_removed,
                "summary": f"{args.kind}:{args.mark_name} " + ("removed" if is_removed else "not recorded")})


def configure(p) -> None:
    p.add_argument("operation", choices=PROFILE_OPERATIONS, help="list · use · mark · unmark")
    p.add_argument("--profile", default=None, help="Shared profile name (repo means the repo profile). mark defaults to the current profile")
    p.add_argument("--kind", default=None, help="mark: state kind (recommended login · data · config)")
    p.add_argument("--name", dest="mark_name", default=None, help="mark: state name (e.g. google · github · corp-sso)")
    p.add_argument("--note", default=None, help="mark: human-readable note (which account — never the password)")


ACTION = Action(name="profile", needs="nothing", run=_web_profile, configure=configure, options=(),
                help="List, choose and mark browser profiles (reuse the same login across repos)",
                example="web profile mark --kind login --name google")
