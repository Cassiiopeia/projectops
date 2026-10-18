"""`cred` — 이름 붙은 자격증명을 저장하고 꺼낸다."""
from __future__ import annotations

import json
import os
import sys

import credentials

from pro_launch.registry import Command
from pro_launch.runtime.output import out


def _prune_old_ssh(plan: list) -> dict:
    """가져온 서버를 옛 `ssh` 섹션에서 지운다. 값이 cred 에 실제로 있는 것만, 지우기 전에 백업한다.

    참조(`ssh_server`)로 만든 것은 옛 섹션이 아직 필요하므로 지우지 않는다.
    """
    import shutil
    moved = {p["name"] for p in plan if p["status"] in ("imported", "exists")
             and not p.get("_raw", {}).get("ssh_server")}
    data = credentials.cfg.load() or {}
    creds = credentials.load_all()
    servers = data.get("ssh")
    key = "instances" if isinstance(servers, dict) else None
    items = (servers.get("instances") if key else servers) or []
    safe = {n for n in moved if creds.get(n, {}).get("host") and not creds[n].get("ssh_server")}
    keep = [s for s in items if s.get("name") not in safe]
    removed = [s.get("name") for s in items if s.get("name") in safe]
    if not removed:
        return {"removed": [], "backup": None}
    path = credentials.cfg.config_path()
    backup = path.with_name(path.name + ".bak-ssh-prune")
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)
    if key:
        servers["instances"] = keep
        data["ssh"] = servers
    elif keep:
        data["ssh"] = keep
    else:
        data.pop("ssh", None)
    credentials._write_config(data)
    return {"removed": removed, "backup": str(backup)}


def _cred_import_ssh(args) -> int:
    """옛 pro-ssh `ssh` 섹션 서버를 launch 자격증명으로 옮긴다.

    **서버 정보는 cred 한 곳에 둔다** — 기본은 host·user·password 값까지 복사한다. 옛 섹션을 계속 쓰고
    싶으면 `--ref`(참조만 만든다, 비밀번호는 옛 섹션에 남는다). `--prune` 은 가져온 서버를 옛 섹션에서
    지운다(config 를 먼저 백업한다). 응답에는 비밀 값을 싣지 않는다.
    """
    existing = credentials.load_all()
    plan = []
    for srv in credentials.ssh_servers():
        name = srv.get("name")
        if not name or not credentials.NAME_RE.match(str(name)):
            plan.append({"name": name, "status": "skipped", "reason": "이름이 없거나 형식이 맞지 않음"})
            continue
        if name in existing:
            plan.append({"name": name, "status": "exists", "reason": "이미 같은 이름의 자격증명이 있음"})
            continue
        if getattr(args, "ref", False):
            fields = {"kind": "ssh", "ssh_server": name}
        else:
            fields = {"kind": "ssh", **{k: srv[k] for k in ("host", "port", "user", "auth", "key_path", "password")
                                        if srv.get(k) not in (None, "")}}
        plan.append({"name": name, "status": "would_import" if args.dry_run else "imported",
                     "fields": credentials.public_view(fields), "_raw": fields})
    if not args.dry_run:
        try:
            for p in plan:
                if p["status"] == "imported":
                    credentials.save_credential(p["name"], p["_raw"])
        except credentials.CredError as e:
            return out({"ok": False, "code": e.code, "error": e.message})
    pruned = None
    if getattr(args, "prune", False) and not args.dry_run:
        pruned = _prune_old_ssh(plan)
    for p in plan:
        p.pop("_raw", None)
    n = sum(1 for p in plan if p["status"] in ("would_import", "imported"))
    return out({"ok": True, "code": "ok", "dry_run": bool(args.dry_run), "servers": plan, "count": n,
                "pruned": pruned,
                "summary": (f"{n}개 가져올 수 있음 (dry-run, 아무것도 쓰지 않음)" if args.dry_run
                            else f"{n}개 가져옴") if plan else "옛 ssh 섹션에 서버가 없습니다",
                "next": ("실제로 옮기려면 --dry-run 을 빼고 다시 부른다. 그다음 cred set --name 이름 --json "
                         "'{\"use_when\":\"...\",\"scope\":\"...\"}' 로 허용 범위를 채운다" if args.dry_run and n
                         else "use_when · scope 를 cred set 으로 채운다. 옛 ssh 섹션은 지우지 않았다")})


# cred policy 의 하위 동작 3개 / 이름을 위치 인자로 받는 동작 3개
POLICY_ACTIONS = ("get", "set", "unset")
NAME_POSITIONAL_ACTIONS = ("show", "set", "unset")


def _cred_policy(args) -> int:
    """로그인 중간 화면 정책 조회·변경 (#905). --name 이 있으면 그 계정, 없으면 전체 기본값"""
    # 입력 확인 (동작, 키, 값)
    if args.policy_action and args.policy_action not in POLICY_ACTIONS:
        return out({"ok": False, "code": "policy_action_required",
                    "error": f"'{args.policy_action}' 는 policy 동작이 아닙니다 ({' · '.join(POLICY_ACTIONS)} 중 하나)",
                    "next": "cred policy get [--name 이름]"})
    if not args.policy_action:
        return out({"ok": False, "code": "policy_action_required", "error": "get · set · unset 중 하나가 필요합니다",
                    "next": "cred policy get [--name 이름]"})
    if args.policy_action in ("set", "unset") and not args.key:
        return out({"ok": False, "code": "key_required",
                    "error": f"--key 가 필요합니다 ({', '.join(credentials.LOGIN_POLICY_KEYS)})",
                    "next": "cred policy get [--name 이름]"})
    if args.policy_action == "set" and not args.value:
        return out({"ok": False, "code": "value_required",
                    "error": f"--value 가 필요합니다 ({', '.join(credentials.LOGIN_POLICY_VALUES)})",
                    "next": "cred policy get [--name 이름]"})
    scope = "credential" if args.name else "global"
    try:
        if args.policy_action == "set":
            credentials.set_login_policy(args.name, args.key, args.value)
            return out({"ok": True, "code": "ok", "name": args.name, "scope": scope,
                        "login_policy": credentials.resolve_login_policy(args.name),
                        "summary": f"{args.key} = {args.value} 저장 ({args.name or '모든 사이트'})",
                        "next": "cred policy get" + (f" --name {args.name}" if args.name else "")})
        if args.policy_action == "unset":
            is_removed = credentials.unset_login_policy(args.name, args.key)
            return out({"ok": is_removed, "code": "ok" if is_removed else "not_found", "name": args.name,
                        "scope": scope, "login_policy": credentials.resolve_login_policy(args.name),
                        "summary": f"{args.key} 지움" if is_removed else f"{args.key} 는 이 층에 저장돼 있지 않습니다",
                        "next": "cred policy get" + (f" --name {args.name}" if args.name else "")})
        if args.name and not credentials.has_credential(args.name):
            raise credentials.CredError("cred_not_found", f"'{args.name}' 자격증명이 없습니다")
        return out({"ok": True, "code": "ok", "name": args.name,
                    "login_policy": credentials.resolve_login_policy(args.name),
                    "summary": "로그인 중간 화면 정책" + (f" ({args.name})" if args.name else " (모든 사이트)"),
                    "next": ("value 가 always·never 인 화면은 묻지 않고 그대로 누른다. "
                             "ask 면 사용자에게 묻고 답을 cred policy set 으로 저장한다")})
    except credentials.CredError as error:
        return out({"ok": False, "code": error.code, "error": error.message,
                    "next": "cred policy get  # 또는 cred list 로 계정 이름을 본다"})


def cmd_cred(args) -> int:
    """자격증명을 저장하고 꺼낸다. 값은 config.json 에만 남고 목록·조회에서는 가려진다."""
    # show · set · unset 뒤의 위치 인자는 이름이다 (cred show <이름> == --name, #931)
    if args.policy_action and args.action in NAME_POSITIONAL_ACTIONS and not args.name:
        args.name, args.policy_action = args.policy_action, None
    elif args.policy_action and args.action in NAME_POSITIONAL_ACTIONS:
        return out({"ok": False, "code": "unexpected_argument",
                    "error": f"이름이 두 번 주어졌습니다: {args.policy_action} 와 --name {args.name}",
                    "next": f"cred {args.action} --name {args.name}"})
    # get · set · unset 은 policy 전용 하위 동작 (다른 동작에 붙으면 조용히 무시하지 않는다)
    if args.policy_action and args.action != "policy":
        return out({"ok": False, "code": "unexpected_argument",
                    "error": f"'{args.policy_action}' 는 cred policy 에서만 쓰는 하위 동작입니다",
                    "next": f"cred {args.action}  # 또는 cred policy {args.policy_action}"})
    if args.action == "list":
        allc = credentials.load_all()
        items = []
        for n, e in sorted(allc.items()):
            items.append({"name": n, "kind": e.get("kind"), "scope": e.get("scope"),
                          "use_when": e.get("use_when"), "has_secret": bool(credentials.secret_values(e))
                          or bool(e.get("ssh_server"))})
        return out({"credentials": items, "count": len(items),
                    "summary": (f"{len(items)}개 저장됨" if items else "저장된 자격증명이 없습니다"),
                    "next": ("use_when · scope 가 지금 하려는 일에 맞는 것만 쓴다. cred show --name 이름"
                             if items else "cred set --name 이름 --json '{\"kind\":\"ssh\",...}'")})

    if args.action == "import-ssh":
        return _cred_import_ssh(args)

    if args.action == "policy":
        return _cred_policy(args)

    try:
        if args.action == "show":
            entry = credentials.resolve(args.name) if args.name else None
            if not entry:
                return out({"ok": False, "code": "name_required", "error": "--name 이 필요합니다"})
            return out({"name": args.name, "credential": credentials.public_view(entry, args.reveal),
                        "summary": f"{args.name} ({entry.get('kind') or 'kind 없음'})",
                        "notes": "값은 가려서 보여 준다. 실행에는 --cred 로 넘기면 된다" if not args.reveal else None})

        if args.action == "set":
            name = credentials.validate_name(args.name)
            try:
                fields = json.loads(args.json_value) if args.json_value else None
            except json.JSONDecodeError as e:
                return out({"ok": False, "code": "bad_json", "error": f"--json 이 올바르지 않습니다: {e}"})
            if args.prompt:
                # 이 맥의 sudo 비밀번호(#784). 채팅이나 파이프로 받지 않는다 — 세션 기록에 평문이 남기 때문이다.
                # 사용자가 터미널에서 직접 치게 하고(입력은 화면에 보이지 않는다) 그 값만 저장한다.
                if not sys.stdin.isatty():
                    return out({"ok": False, "code": "no_tty",
                                "error": "비밀번호는 터미널에서 직접 입력해야 합니다 (채팅·파이프로는 받지 않습니다)",
                                "next": f"사용자가 터미널에서: launch_cli.py cred set --name {name} --prompt"})
                import getpass
                pw = getpass.getpass("이 맥의 sudo 비밀번호: ")
                if not pw:
                    return out({"ok": False, "code": "empty_password", "error": "비밀번호가 비었습니다"})
                fields = {"kind": "local", "use_when": "이 맥에서 관리자 권한(sudo)이 필요할 때",
                          **(fields or {}), "sudo_password": pw}
            f = credentials.save_credential(name, fields or {}, replace=args.replace)
            saved = credentials.load_all().get(name, {})
            missing = [k for k in ("kind", "use_when") if not saved.get(k)]
            return out({"file": str(f), "name": name, "credential": credentials.public_view(saved),
                        "summary": f"{name} 저장 완료",
                        "hint": (f"{'·'.join(missing)} 를 채워 두면 agent 가 언제 써도 되는지 판단할 수 있다"
                                 if missing else None)})

        if args.action == "unset":
            ok = credentials.delete_credential(credentials.validate_name(args.name))
            return out({"name": args.name, "ok": ok, "code": "ok" if ok else "not_found",
                        "summary": f"{args.name} 지움" if ok else f"{args.name} 가 없습니다"})
    except credentials.CredError as e:
        return out({"ok": False, "code": e.code, "error": e.message, "next": e.next_hint})
    return out({"ok": False, "code": "unknown_action", "error": args.action})


def configure_cred(p) -> None:
    p.add_argument("action", choices=["list", "show", "set", "unset", "import-ssh", "policy"])
    # policy 전용: get · set · unset (로그인 중간 화면 정책, #905). show·set·unset 에서는 이름으로 읽는다 (#931)
    p.add_argument("policy_action", nargs="?", default=None, metavar="policy_action|name")
    p.add_argument("--name", default=None)
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="import-ssh 때 아무것도 쓰지 않고 옮길 목록만 보여 준다 (비밀 값은 가려서)")
    p.add_argument("--inline", action="store_true",
                   help="(기본 동작) import-ssh 때 host·user·password 값까지 복사한다")
    p.add_argument("--ref", action="store_true",
                   help="import-ssh 때 값을 복사하지 않고 옛 ssh 섹션을 참조만 한다 (비밀번호가 두 곳에 남는다)")
    p.add_argument("--prune", action="store_true",
                   help="import-ssh 뒤에 가져온 서버를 옛 ssh 섹션에서 지운다 (config 를 먼저 백업)")
    p.add_argument("--json", dest="json_value", default=None,
                   help='저장할 내용(JSON). 예: {"kind":"ssh","host":"h","port":22,"user":"u","use_when":"..."}')
    p.add_argument("--replace", action="store_true", help="set 때 기존 항목을 합치지 않고 통째로 바꾼다")
    # --key · --value 는 choices 를 두지 않는다 — 잘못된 값도 JSON code 로 돌려주기 위해
    p.add_argument("--key", default=None, help="policy: trust_device · keep_signed_in · skip_nags")
    p.add_argument("--value", default=None, help="policy set: ask · always · never")
    p.add_argument("--reveal", action="store_true", help="show 때 비밀 값도 그대로 보여 준다 (꼭 필요할 때만)")
    p.add_argument("--prompt", action="store_true",
                   help="set 때 이 맥의 sudo 비밀번호를 터미널에서 직접 입력받아 저장한다 (화면에 안 보임, TTY 필요)")


COMMANDS = [
    Command(name="cred", help="이름 붙은 자격증명을 저장하고 꺼낸다 (다음 실행에서 다시 묻지 않는다)", run=cmd_cred,
            configure=configure_cred),
]
