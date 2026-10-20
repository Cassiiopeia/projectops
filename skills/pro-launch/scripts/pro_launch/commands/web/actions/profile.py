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
                    "summary": f"지금 프로필 {current} · 공용 프로필 {len(names) - 1}개",
                    "next": "web open --profile <이름> 으로 레포를 넘어 같은 로그인을 쓴다"})
    if operation == "use":
        name = args.profile or browser_profiles.REPO_PROFILE_NAME
        if name != browser_profiles.REPO_PROFILE_NAME and not browser_profiles.is_valid_profile_name(name):
            return out({"ok": False, "code": "bad_args", "error": f"프로필 이름은 영문·숫자·._- 40자 이내: {name}"})
        browser_profiles.choose_profile(root, name)
        return out({"action": "profile", "operation": "use", "current": name,
                    "summary": f"이 레포는 이제 {name} 프로필을 쓴다", "next": "web open"})
    if not args.kind or not args.mark_name:
        return out({"ok": False, "code": "args_required", "error": "--kind 와 --name 이 필요하다",
                    "next": "web profile mark --kind login --name google --note '사내 계정'"})
    key = browser_profiles.profile_mark_key(root, args.profile)
    if operation == "mark":
        mark = device_marks.add_mark(key, args.kind, args.mark_name, args.note)
        return out({"action": "profile", "operation": "mark", "key": key, "mark": mark,
                    "summary": f"{key} 에 {args.kind}:{args.mark_name} 기록 — 정리에서 보호되고 open --need 가 고른다",
                    "next": f"다른 레포에서는 web open --need {args.kind}:{args.mark_name}"})
    is_removed = device_marks.remove_mark(key, args.kind, args.mark_name)
    return out({"action": "profile", "operation": "unmark", "key": key, "removed": is_removed,
                "summary": f"{args.kind}:{args.mark_name} " + ("지움" if is_removed else "기록이 없다")})


def configure(p) -> None:
    p.add_argument("operation", choices=PROFILE_OPERATIONS, help="list · use · mark · unmark")
    p.add_argument("--profile", default=None, help="공용 프로필 이름 (repo 면 레포 프로필). mark 는 없으면 지금 프로필")
    p.add_argument("--kind", default=None, help="mark: 상태 종류 (권장 login · data · config)")
    p.add_argument("--name", dest="mark_name", default=None, help="mark: 상태 이름 (예: google · github · 사내SSO)")
    p.add_argument("--note", default=None, help="mark: 사람이 읽을 설명 (어느 계정인지 — 비밀번호는 적지 않는다)")


ACTION = Action(name="profile", needs="nothing", run=_web_profile, configure=configure, options=(),
                help="브라우저 프로필 보기 · 고르기 · 로그인 상태 기록 (레포를 넘어 같은 로그인 쓰기)",
                example="web profile mark --kind login --name google")
