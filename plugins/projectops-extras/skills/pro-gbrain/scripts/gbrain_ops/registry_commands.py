"""registry add-provisioner | import | export: get a brain server entry onto this machine without hand-editing config.json
Plan by default; --apply --yes writes (backup first, missing keys only). Secrets are never accepted or copied:
the admin key is a credential store name, and secret-looking keys in an imported file are dropped and reported.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from . import common, credentials, provisioner as provisioner_module, registry_store

ACTIONS = ("add-provisioner", "import", "export")
DEFAULT_CREDENTIAL_FIELD = "token"
# Keys never copied from an imported file (the registry holds references only)
SECRET_KEY_PATTERN = re.compile(r"(password|passwd|secret|token|api_?key|private_?key|database_url|connection_url)$", re.IGNORECASE)
# credential / credential_field name a store entry, they are not secrets
REFERENCE_KEYS = ("credential", "credential_field", "token_cred", "mcp_server_name")


def register(sub) -> dict:
    parser = sub.add_parser("registry", help="add a brain server entry, or import/export the brains section (plan by default)")
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("--name", help="add-provisioner: entry name, e.g. brain-server")
    parser.add_argument("--base-url", dest="base_url", help="add-provisioner: provisioner API root, e.g. https://brain.example.com/api")
    parser.add_argument("--credential", help="add-provisioner: credential store entry holding the admin key (a name, never the key)")
    parser.add_argument("--credential-field", dest="credential_field", default=DEFAULT_CREDENTIAL_FIELD)
    parser.add_argument("--type", dest="provisioner_type", default=provisioner_module.SUPPORTED_TYPES[0],
                        choices=provisioner_module.SUPPORTED_TYPES)
    parser.add_argument("--auth-header", dest="auth_header", default="X-API-Key")
    parser.add_argument("--supports-dry-run", dest="supports_dry_run", action="store_true",
                        help="only when the server implements dry_run")
    parser.add_argument("--file", help="import: JSON file from registry export (or a whole config.json)")
    parser.add_argument("--out", help="export: file to write (600)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true")
    return {"registry": cmd_registry}


def cmd_registry(args) -> dict:
    return {"add-provisioner": _add_provisioner, "import": _import, "export": _export}[args.action](args)


# ---------- add-provisioner ----------
def _add_provisioner(args) -> dict:
    missing = [flag for flag, value in (("--name", args.name), ("--base-url", args.base_url), ("--credential", args.credential))
               if not value]
    if missing:
        return {"ok": False, "code": "bad_args", "summary": f"missing {', '.join(missing)}",
                "next": "registry add-provisioner --name brain-server --base-url https://<host>/api --credential <cred name>"}
    if not args.base_url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        return {"ok": False, "code": "provisioner_bad_url", "summary": "base_url must be https (or a local test address)",
                "next": "pass the https API root of the brain server"}
    entry = {"kind": registry_store.PROVISIONER_KIND, "provisioner": {
        "type": args.provisioner_type, "base_url": args.base_url.rstrip("/"), "auth_header": args.auth_header,
        "credential": args.credential, "credential_field": args.credential_field,
        **({"supports_dry_run": True} if args.supports_dry_run else {})}}
    has_key = _has_credential(args.credential, args.credential_field)
    store_hint = (f"store the admin key: python3 ~/.projectops/bin/projectops_cli.py launch cred set --name {args.credential} "
                  f"--secret-field {args.credential_field} --prompt (in a separate terminal) or --from-file FILE --delete-after")
    plan = _merge_plan({args.name: entry})
    if not (args.apply and args.yes):
        return {"ok": True, "code": "plan", **plan, "admin_key_stored": has_key,
                "summary": f"add brain server {args.name} ({args.base_url}) to the private registry",
                "next": f"ask once, then: registry add-provisioner --name {args.name} --base-url {args.base_url} "
                        f"--credential {args.credential} --apply --yes"}
    result = _merge_apply({args.name: entry})
    return {"ok": True, "code": "registered", **result, "admin_key_stored": has_key,
            "summary": f"brain server {args.name} registered" + ("" if has_key else "; the admin key is not stored yet"),
            "next": (store_hint + "; then gbrain_cli.py status") if not has_key else "gbrain_cli.py status"}


def _has_credential(name: str, field: str) -> bool:
    try:
        credentials.read_secret(name, field)
        return True
    except credentials.CredentialError:
        return False


# ---------- import / export ----------
def _export(args) -> dict:
    brains = registry_store.brains(registry_store.load_section())
    if not brains:
        return {"ok": False, "code": "nothing_to_export", "summary": "this machine's registry has no infra.brains entries",
                "next": "registry add-provisioner ... on this machine, or export from the machine that has them"}
    cleaned, dropped = _drop_secrets(brains)
    payload = {"project-blueprint": {"infra": {"brains": cleaned}}}
    if not args.out:
        return {"ok": True, "code": "plan", "brains": sorted(cleaned), "dropped_secret_keys": dropped,
                "summary": f"{len(cleaned)} brain entr(ies) ready to export (references only)",
                "next": "registry export --out FILE"}
    out_path = Path(args.out).expanduser()
    file_descriptor = os.open(str(out_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, common.PRIVATE_FILE_MODE)
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
    return {"ok": True, "code": "exported", "file": str(out_path), "brains": sorted(cleaned), "dropped_secret_keys": dropped,
            "summary": f"exported {len(cleaned)} brain entr(ies) to {out_path} (600, no secrets)",
            "next": "copy the file to the other machine, then there: registry import --file FILE"}


def _import(args) -> dict:
    if not args.file:
        return {"ok": False, "code": "bad_args", "summary": "missing --file", "next": "registry import --file FILE"}
    try:
        data = json.loads(Path(args.file).expanduser().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        return {"ok": False, "code": "import_unreadable", "summary": f"cannot read {args.file}: {type(error).__name__}",
                "next": "pass the JSON file written by registry export (or a config.json)"}
    section = data.get(registry_store.SECTION, data) if isinstance(data, dict) else {}
    incoming = registry_store.brains(section)
    if not incoming:
        return {"ok": False, "code": "nothing_to_import", "summary": "the file has no project-blueprint infra.brains entries",
                "next": "on the other machine: registry export --out FILE"}
    cleaned, dropped = _drop_secrets(incoming)
    plan = _merge_plan(cleaned)
    if not (args.apply and args.yes):
        return {"ok": True, "code": "plan", **plan, "dropped_secret_keys": dropped,
                "summary": f"import {len(cleaned)} brain entr(ies); existing values are kept",
                "next": f"ask once, then: registry import --file {args.file} --apply --yes"}
    result = _merge_apply(cleaned)
    credential_names = sorted({str((entry.get("provisioner") or {}).get("credential")) for entry in cleaned.values()
                               if isinstance(entry, dict) and (entry.get("provisioner") or {}).get("credential")})
    return {"ok": True, "code": "imported", **result, "dropped_secret_keys": dropped, "credentials_to_store": credential_names,
            "summary": f"imported {len(result['added_entries']) + len(result['merged_entries'])} brain entr(ies)",
            "next": ("store the admin key(s) on this machine (" + ", ".join(credential_names) + ") with launch cred set; then "
                     if credential_names else "") + "gbrain_cli.py status"}


def _drop_secrets(value, path: str = "") -> tuple:
    """Copy without secret-looking keys > (cleaned, dropped key paths)"""
    if not isinstance(value, dict):
        return value, []
    cleaned, dropped = {}, []
    for key, item in value.items():
        child_path = f"{path}.{key}" if path else key
        if SECRET_KEY_PATTERN.search(key) and key not in REFERENCE_KEYS:
            dropped.append(child_path)
            continue
        cleaned[key], child_dropped = _drop_secrets(item, child_path)
        dropped += child_dropped
    return cleaned, dropped


# ---------- shared merge (missing keys only) ----------
def _merge_into(existing: dict, incoming: dict) -> list:
    """Add missing keys recursively; returns conflicting key paths (existing different values are kept)"""
    conflicts = []
    for key, value in incoming.items():
        if key not in existing:
            existing[key] = value
        elif isinstance(existing[key], dict) and isinstance(value, dict):
            conflicts += [f"{key}.{child}" for child in _merge_into(existing[key], value)]
        elif existing[key] != value:
            conflicts.append(key)
    return conflicts


def _merge_plan(entries: dict) -> dict:
    current = registry_store.brains(registry_store.load_section())
    added = [name for name in entries if name not in current]
    merged = [name for name in entries if name in current]
    conflicts = {}
    for name in merged:
        probe = json.loads(json.dumps(current[name])) if isinstance(current[name], dict) else {}
        found = _merge_into(probe, entries[name]) if isinstance(entries[name], dict) else []
        if found:
            conflicts[name] = found
    return {"added_entries": added, "merged_entries": merged, "kept_conflicts": conflicts}


def _merge_apply(entries: dict) -> dict:
    plan = _merge_plan(entries)
    data = registry_store.load_config() or {}
    config_file = credentials.config_path()
    backup_path = None
    if config_file.exists():
        backup_path = config_file.with_name(f"{config_file.name}.bak-pro-gbrain-{common.compact_timestamp()}")
        shutil.copyfile(config_file, backup_path)
        backup_path.chmod(common.PRIVATE_FILE_MODE)
    brains = data.setdefault(registry_store.SECTION, {}).setdefault("infra", {}).setdefault("brains", {})
    for name, entry in entries.items():
        if isinstance(brains.get(name), dict) and isinstance(entry, dict):
            _merge_into(brains[name], entry)
        else:
            brains.setdefault(name, entry)
    credentials.write_config_atomic(data)
    return {**plan, "backup": str(backup_path) if backup_path else None}
