"""`access` — 서버에 붙는 법을 적어 두고 꺼내 쓴다."""
from __future__ import annotations

import json

from common.access import access_path, find_secrets, load_access, load_status, needs_verify, reset_status, save_access

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root, state_home
from pro_launch.runtime.output import out


def cmd_access(args) -> int:
    """이 프로젝트에 어떻게 붙는지를 적어 두고 꺼내 쓴다. 비밀번호는 **값을 적지 않는다.**"""
    root = project_root(args)
    state_home(root)
    data = load_access(root)

    if args.action == "show":
        status = {k: v for k, v in load_status(root).items() if k in data}
        doubt = sorted(k for k, v in status.items() if needs_verify(v))
        return out({"file": str(access_path(root)), "access": data,
                    "status": status or None,
                    "verify": doubt or None,
                    "summary": (f"{', '.join(data)} recorded" if data else "Nothing recorded yet"),
                    "next": (None if data else
                             "Read the code to learn how to connect, then access set --key db --json '{...}'")})

    if args.action == "set":
        if not args.key:
            return out({"ok": False, "code": "key_required",
                        "error": "--key is required (db · logs · base_url, etc.)"})
        try:
            value = json.loads(args.json_value) if args.json_value else None
        except json.JSONDecodeError as e:
            return out({"ok": False, "code": "bad_json", "error": f"Invalid --json: {e}"})
        if value is None:
            return out({"ok": False, "code": "value_required", "error": "--json is required"})
        leaked = find_secrets(json.dumps(value, ensure_ascii=False))
        if leaked and not args.allow_secret:
            return out({"ok": False, "code": "secret_in_value",
                        "error": "The value contains something that looks like a secret", "found": leaked[:5],
                        "hint": ('Do not write secrets to access. Save the value with cred set --name <name> --json \'{...}\' and '
                                 'write only {"cred":"<name>"} to access (to read it from an environment variable: {"password_env":"APP_DB_PASSWORD"})')})
        data[args.key] = value
        f = save_access(root, data)
        reset_status(root, args.key)   # 방법이 바뀌었으면 옛 성적은 의미가 없다
        return out({"file": str(f), "key": args.key, "access": data,
                    "summary": f"{args.key} recorded"})

    if args.action == "unset":
        if not args.key:
            # set 과 같게 --key 를 요구한다. 없으면 "None 가 없습니다" 로 성공 처리돼 오해를 부른다 (#713)
            return out({"ok": False, "code": "key_required",
                        "error": "--key is required (db · logs · base_url, etc.)"})
        if args.key in data:
            del data[args.key]
            save_access(root, data)
            reset_status(root, args.key)
            return out({"key": args.key, "access": data, "summary": f"{args.key} removed"})
        return out({"key": args.key, "access": data, "code": "not_found",
                    "summary": f"{args.key} not found"})
    return out({"ok": False, "code": "unknown_action", "error": args.action})


def configure_access(p) -> None:
    p.add_argument("action", choices=["show", "set", "unset"])
    p.add_argument("--root", default=".")
    p.add_argument("--key", default=None, help="db · logs · base_url, etc.")
    p.add_argument("--json", dest="json_value", default=None,
                   help='Content to record (JSON). e.g. {"how":"ssh","engine":"postgres",...}')
    p.add_argument("--allow-secret", dest="allow_secret", action="store_true",
                   help="Ignore the secret warning (not recommended)")


COMMANDS = [
    Command(name="access", help="Record how to connect and reuse it", run=cmd_access,
            configure=configure_access),
]
