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
            plan.append({"name": name, "status": "skipped", "reason": "name missing or malformed"})
            continue
        if name in existing:
            plan.append({"name": name, "status": "exists", "reason": "a credential with this name already exists"})
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
                "summary": (f"{n} can be imported (dry-run, nothing written)" if args.dry_run
                            else f"{n} imported") if plan else "No servers in the old ssh section",
                "next": ("To import for real, run again without --dry-run. Then fill the allowed scope with cred set --name <name> --json "
                         "'{\"use_when\":\"...\",\"scope\":\"...\"}'" if args.dry_run and n
                         else "Fill use_when · scope with cred set. The old ssh section was not removed")})


# cred policy 의 하위 동작 3개 / 이름을 위치 인자로 받는 동작 3개
POLICY_ACTIONS = ("get", "set", "unset")
NAME_POSITIONAL_ACTIONS = ("show", "set", "unset")


def _cred_policy(args) -> int:
    """로그인 중간 화면 정책 조회·변경 (#905). --name 이 있으면 그 계정, 없으면 전체 기본값"""
    # 입력 확인 (동작, 키, 값)
    if args.policy_action and args.policy_action not in POLICY_ACTIONS:
        return out({"ok": False, "code": "policy_action_required",
                    "error": f"'{args.policy_action}' is not a policy action (one of {' · '.join(POLICY_ACTIONS)})",
                    "next": "cred policy get [--name <name>]"})
    if not args.policy_action:
        return out({"ok": False, "code": "policy_action_required", "error": "One of get · set · unset is required",
                    "next": "cred policy get [--name <name>]"})
    if args.policy_action in ("set", "unset") and not args.key:
        return out({"ok": False, "code": "key_required",
                    "error": f"--key is required ({', '.join(credentials.LOGIN_POLICY_KEYS)})",
                    "next": "cred policy get [--name <name>]"})
    if args.policy_action == "set" and not args.value:
        return out({"ok": False, "code": "value_required",
                    "error": f"--value is required ({', '.join(credentials.LOGIN_POLICY_VALUES)})",
                    "next": "cred policy get [--name <name>]"})
    scope = "credential" if args.name else "global"
    try:
        if args.policy_action == "set":
            credentials.set_login_policy(args.name, args.key, args.value)
            return out({"ok": True, "code": "ok", "name": args.name, "scope": scope,
                        "login_policy": credentials.resolve_login_policy(args.name),
                        "summary": f"Saved {args.key} = {args.value} ({args.name or 'all sites'})",
                        "next": "cred policy get" + (f" --name {args.name}" if args.name else "")})
        if args.policy_action == "unset":
            is_removed = credentials.unset_login_policy(args.name, args.key)
            return out({"ok": is_removed, "code": "ok" if is_removed else "not_found", "name": args.name,
                        "scope": scope, "login_policy": credentials.resolve_login_policy(args.name),
                        "summary": f"Removed {args.key}" if is_removed else f"{args.key} is not stored at this level",
                        "next": "cred policy get" + (f" --name {args.name}" if args.name else "")})
        if args.name and not credentials.has_credential(args.name):
            raise credentials.CredError("cred_not_found", f"No credential named '{args.name}'")
        return out({"ok": True, "code": "ok", "name": args.name,
                    "login_policy": credentials.resolve_login_policy(args.name),
                    "summary": "Login interstitial policy" + (f" ({args.name})" if args.name else " (all sites)"),
                    "next": ("Screens whose value is always·never are answered without asking. "
                             "For ask, ask the user and save the answer with cred policy set")})
    except credentials.CredError as error:
        return out({"ok": False, "code": error.code, "error": error.message,
                    "next": "cred policy get  # or see account names with cred list"})


def cmd_cred(args) -> int:
    """자격증명을 저장하고 꺼낸다. 값은 config.json 에만 남고 목록·조회에서는 가려진다."""
    # show · set · unset 뒤의 위치 인자는 이름이다 (cred show <이름> == --name, #931)
    if args.policy_action and args.action in NAME_POSITIONAL_ACTIONS and not args.name:
        args.name, args.policy_action = args.policy_action, None
    elif args.policy_action and args.action in NAME_POSITIONAL_ACTIONS:
        return out({"ok": False, "code": "unexpected_argument",
                    "error": f"Name given twice: {args.policy_action} and --name {args.name}",
                    "next": f"cred {args.action} --name {args.name}"})
    # get · set · unset 은 policy 전용 하위 동작 (다른 동작에 붙으면 조용히 무시하지 않는다)
    if args.policy_action and args.action != "policy":
        return out({"ok": False, "code": "unexpected_argument",
                    "error": f"'{args.policy_action}' is a sub-action used only with cred policy",
                    "next": f"cred {args.action}  # or cred policy {args.policy_action}"})
    if args.action == "list":
        allc = credentials.load_all()
        items = []
        for n, e in sorted(allc.items()):
            items.append({"name": n, "kind": e.get("kind"), "scope": e.get("scope"),
                          "use_when": e.get("use_when"), "has_secret": bool(credentials.secret_values(e))
                          or bool(e.get("ssh_server"))})
        return out({"credentials": items, "count": len(items),
                    "summary": (f"{len(items)} saved" if items else "No saved credentials"),
                    "next": ("Use only those whose use_when · scope fit the task at hand. cred show --name <name>"
                             if items else "cred set --name <name> --json '{\"kind\":\"ssh\",...}'")})

    if args.action == "import-ssh":
        return _cred_import_ssh(args)

    if args.action == "policy":
        return _cred_policy(args)

    try:
        if args.action == "show":
            entry = credentials.resolve(args.name) if args.name else None
            if not entry:
                return out({"ok": False, "code": "name_required", "error": "--name is required"})
            return out({"name": args.name, "credential": credentials.public_view(entry, args.reveal),
                        "summary": f"{args.name} ({entry.get('kind') or 'no kind'})",
                        "notes": "Values are masked. Pass it to commands with --cred" if not args.reveal else None})

        if args.action == "set":
            name = credentials.validate_name(args.name)
            try:
                fields = json.loads(args.json_value) if args.json_value else None
            except json.JSONDecodeError as e:
                return out({"ok": False, "code": "bad_json", "error": f"Invalid --json: {e}"})
            if args.prompt:
                # 이 맥의 sudo 비밀번호(#784). 채팅이나 파이프로 받지 않는다 — 세션 기록에 평문이 남기 때문이다.
                # 사용자가 터미널에서 직접 치게 하고(입력은 화면에 보이지 않는다) 그 값만 저장한다.
                if not sys.stdin.isatty():
                    return out({"ok": False, "code": "no_tty",
                                "error": "The password must be typed in a terminal (not accepted via chat or pipe)",
                                "next": f"User, in a terminal: launch_cli.py cred set --name {name} --prompt"})
                import getpass
                # kind: ssh 면 서버 접속 비밀번호(#946), 아니면 이 맥의 sudo 비밀번호
                is_ssh_server = (fields or {}).get("kind") == "ssh"
                pw = getpass.getpass("Server SSH password: " if is_ssh_server else "sudo password for this Mac: ")
                if not pw:
                    return out({"ok": False, "code": "empty_password", "error": "Password is empty"})
                if is_ssh_server:
                    fields = {**fields, "password": pw}
                else:
                    fields = {"kind": "local", "use_when": "When admin rights (sudo) are needed on this Mac",
                              **(fields or {}), "sudo_password": pw}
            f = credentials.save_credential(name, fields or {}, replace=args.replace)
            saved = credentials.load_all().get(name, {})
            missing = [k for k in ("kind", "use_when") if not saved.get(k)]
            return out({"file": str(f), "name": name, "credential": credentials.public_view(saved),
                        "summary": f"Saved {name}",
                        "hint": (f"Fill {'·'.join(missing)} so agents can judge when it may be used"
                                 if missing else None)})

        if args.action == "unset":
            ok = credentials.delete_credential(credentials.validate_name(args.name))
            return out({"name": args.name, "ok": ok, "code": "ok" if ok else "not_found",
                        "summary": f"Removed {args.name}" if ok else f"{args.name} not found"})
    except credentials.CredError as e:
        return out({"ok": False, "code": e.code, "error": e.message, "next": e.next_hint})
    return out({"ok": False, "code": "unknown_action", "error": args.action})


def configure_cred(p) -> None:
    p.add_argument("action", choices=["list", "show", "set", "unset", "import-ssh", "policy"])
    # policy 전용: get · set · unset (로그인 중간 화면 정책, #905). show·set·unset 에서는 이름으로 읽는다 (#931)
    p.add_argument("policy_action", nargs="?", default=None, metavar="policy_action|name")
    p.add_argument("--name", default=None)
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="import-ssh: write nothing, only list what would be imported (secrets masked)")
    p.add_argument("--inline", action="store_true",
                   help="(default) import-ssh: copy host·user·password values too")
    p.add_argument("--ref", action="store_true",
                   help="import-ssh: only reference the old ssh section instead of copying (password stays in two places)")
    p.add_argument("--prune", action="store_true",
                   help="after import-ssh, remove the imported servers from the old ssh section (config is backed up first)")
    p.add_argument("--json", dest="json_value", default=None,
                   help='Content to save (JSON). e.g. {"kind":"ssh","host":"h","port":22,"user":"u","use_when":"..."}')
    p.add_argument("--replace", action="store_true", help="set: replace the entry instead of merging")
    # --key · --value 는 choices 를 두지 않는다 — 잘못된 값도 JSON code 로 돌려주기 위해
    p.add_argument("--key", default=None, help="policy: trust_device · keep_signed_in · skip_nags")
    p.add_argument("--value", default=None, help="policy set: ask · always · never")
    p.add_argument("--reveal", action="store_true", help="show: reveal secret values too (only when really needed)")
    p.add_argument("--prompt", action="store_true",
                   help="set: read the password typed in the terminal and save it (hidden, needs a TTY). Server password if --json kind is ssh, otherwise the sudo password for this Mac")


COMMANDS = [
    Command(name="cred", help="Save and retrieve named credentials (not asked again on the next run)", run=cmd_cred,
            configure=configure_cred),
]
