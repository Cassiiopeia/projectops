"""`cred` — save and read named credentials."""
from __future__ import annotations

import json
import os
import sys

import credentials

from pro_launch.registry import Command
from pro_launch.runtime.output import out


def _prune_old_ssh(plan: list) -> dict:
    """Remove imported servers from the old `ssh` section. Only those actually present in cred, backed up before removal.

    Ones created as references (`ssh_server`) still need the old section, so they are not removed.
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
    """Move servers from the old pro-ssh `ssh` section into launch credentials.

    **Server info lives in cred only** — by default host, user and password values are copied. To keep using the old
    section, use `--ref` (creates a reference only; the password stays in the old section). `--prune` removes imported servers
    from the old section (backs up config first). Secret values are never put in the response.
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


def _cred_check(_args) -> int:
    """Read-only: config references to missing credentials, credentials no section references (names only)"""
    try:
        report = credentials.credential_store.check_credential_references()
    except credentials.credential_store.CredentialError as error:
        return out({"ok": False, "code": error.code, "error": error.message})
    missing_count = len(report["missing"])
    return out({"ok": missing_count == 0, "code": "ok" if missing_count == 0 else "missing_credentials",
                **report,
                "summary": (f"{len(report['references'])} reference(s), {missing_count} missing, "
                            f"{len(report['unreferenced'])} stored but unreferenced"),
                "next": (f"cred set --name {report['missing'][0]['name']} --secret-field token --prompt  "
                         "# the user types it in a terminal" if missing_count
                         else "Unreferenced is not unused: commands also take names directly (--cred)")})


def _cred_migrate_github_pat(args) -> int:
    """Move github.global_pat into the store (plan without --yes; values never in the response)"""
    cred_name = args.name or credentials.credential_store.GITHUB_PAT_DEFAULT_CRED_NAME
    try:
        credentials.validate_name(cred_name)
        store = credentials.credential_store
        result = store.apply_github_pat_migration(cred_name) if args.yes else store.plan_github_pat_migration(cred_name)
    except (credentials.CredError, credentials.credential_store.CredentialError) as error:
        return out({"ok": False, "code": error.code, "error": error.message})
    state = result["state"]
    summaries = {
        "ready": "github.global_pat can move into the credential store (nothing written)",
        "migrated": f"Moved github.global_pat into credential '{cred_name}'",
        "already_migrated": "Already migrated: github.global_pat_cred names the stored PAT",
        "no_global_pat": "No github.global_pat to migrate",
        "name_taken": f"A credential named '{cred_name}' already exists; pick another with --name",
    }
    return out({"ok": state != "name_taken", "code": state, **result, "summary": summaries[state],
                "next": ("Ask the user once; with a yes: cred migrate-github-pat --yes. "
                         "projectops older than this release reads only github.global_pat" if state == "ready"
                         else "cred check")})


def _secret_from_input(args, field: str) -> tuple[str | None, dict | None]:
    """Secret value for --secret-field: hidden terminal input (--prompt) or a named env var (--from-env)"""
    if args.from_env:
        value = os.environ.get(args.from_env, "")
        if not value:
            return None, {"ok": False, "code": "env_empty", "error": f"Environment variable {args.from_env} is empty"}
        return value, None
    if not sys.stdin.isatty():
        return None, {"ok": False, "code": "no_tty",
                      "error": "The value must be typed in a terminal (not accepted via chat or pipe)",
                      "next": f"User, in a terminal: launch_cli.py cred set --name {args.name} --secret-field {field} --prompt"}
    import getpass
    value = getpass.getpass(f"{field} for {args.name} (hidden): ")
    if not value:
        return None, {"ok": False, "code": "empty_password", "error": "Value is empty"}
    return value, None


# 3 sub-actions of cred policy / 3 actions that take the name as a positional argument
POLICY_ACTIONS = ("get", "set", "unset")
NAME_POSITIONAL_ACTIONS = ("show", "set", "unset")


def _cred_policy(args) -> int:
    """Read or change the login interstitial policy (#905). With --name, that account; otherwise the global default"""
    # Validate input (action, key, value)
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
    """Save and read credentials. Values stay only in config.json and are masked in list and show."""
    # The positional argument after show · set · unset is the name (cred show <name> == --name, #931)
    if args.policy_action and args.action in NAME_POSITIONAL_ACTIONS and not args.name:
        args.name, args.policy_action = args.policy_action, None
    elif args.policy_action and args.action in NAME_POSITIONAL_ACTIONS:
        return out({"ok": False, "code": "unexpected_argument",
                    "error": f"Name given twice: {args.policy_action} and --name {args.name}",
                    "next": f"cred {args.action} --name {args.name}"})
    # get · set · unset are policy-only sub-actions (not silently ignored on other actions)
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

    if args.action == "check":
        return _cred_check(args)

    if args.action == "migrate-github-pat":
        return _cred_migrate_github_pat(args)

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
            if args.secret_field and (args.prompt or args.from_env):
                # Any secret field (token, api_key ...) without the value passing through chat or argv
                secret_value, error_payload = _secret_from_input(args, args.secret_field)
                if error_payload:
                    return out(error_payload)
                fields = {**(fields or {}), args.secret_field: secret_value}
            elif args.from_env:
                return out({"ok": False, "code": "secret_field_required",
                            "error": "--from-env needs --secret-field <field>",
                            "next": f"cred set --name {name} --secret-field token --from-env {args.from_env}"})
            elif args.prompt:
                # This Mac's sudo password (#784). Never taken via chat or pipe — the session log would keep it in plain text.
                # The user types it in the terminal (input is hidden) and only that value is saved.
                if not sys.stdin.isatty():
                    return out({"ok": False, "code": "no_tty",
                                "error": "The password must be typed in a terminal (not accepted via chat or pipe)",
                                "next": f"User, in a terminal: launch_cli.py cred set --name {name} --prompt"})
                import getpass
                # kind: ssh means the server login password (#946); otherwise this Mac's sudo password
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
    p.add_argument("action", choices=["list", "show", "set", "unset", "import-ssh", "policy", "check",
                                      "migrate-github-pat"])
    # policy only: get · set · unset (login interstitial policy, #905). show·set·unset read it as the name (#931)
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
    # --key · --value have no choices — so invalid values still come back as a JSON code
    p.add_argument("--key", default=None, help="policy: trust_device · keep_signed_in · skip_nags")
    p.add_argument("--value", default=None, help="policy set: ask · always · never")
    p.add_argument("--secret-field", dest="secret_field", default=None,
                   help="set: field that receives the secret from --prompt (hidden) or --from-env (e.g. token)")
    p.add_argument("--from-env", dest="from_env", default=None,
                   help="set: read the --secret-field value from this environment variable (never from argv)")
    p.add_argument("--yes", action="store_true", help="migrate-github-pat: apply (without it, plan only)")
    p.add_argument("--reveal", action="store_true", help="show: reveal secret values too (only when really needed)")
    p.add_argument("--prompt", action="store_true",
                   help="set: read the password typed in the terminal and save it (hidden, needs a TTY). Server password if --json kind is ssh, otherwise the sudo password for this Mac")


COMMANDS = [
    Command(name="cred", help="Save and retrieve named credentials (not asked again on the next run)", run=cmd_cred,
            configure=configure_cred),
]
