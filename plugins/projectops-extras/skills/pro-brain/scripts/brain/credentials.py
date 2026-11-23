"""Credential store accessor shared by every skill: names in, values to code only, never to stdout or logs.

Store: config.json `launch.credentials.<name>` (key kept for compatibility; the docs call it the credential store).
Other config sections reference an entry by name (`credential`, `*_cred`, `*_credential`) and never hold the value.
Standard library only, no module-level `common` import: extras skills ship a generated copy (scripts/sync_extras.py).
Rules: skills/references/config-rules.md §9.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

# Store location inside config.json (launch.credentials, kept from pro-launch for compatibility)
STORE_SECTION = "launch"
STORE_KEY = "credentials"
# Credential name: letter or digit first, then letters, digits, `._-` (64 chars max)
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# Field names whose values are secret (masked in every view)
SECRET_KEY_MARKERS = ("password", "passwd", "token", "secret", "passphrase", "api_key", "apikey", "private_key")
# Reference keys elsewhere in config: exact `credential`, or a `_cred` / `_credential` suffix (e.g. token_cred)
REFERENCE_KEY_EXACT = "credential"
REFERENCE_KEY_SUFFIXES = ("_cred", "_credential")
# github.global_pat migration target (store entry name + reference key left in the github section)
GITHUB_PAT_DEFAULT_CRED_NAME = "github-global-pat"
GITHUB_PAT_REFERENCE_KEY = "global_pat_cred"


class CredentialError(Exception):
    """Lookup or save failure. `code` becomes the JSON response code; messages carry names, never values."""

    def __init__(self, code: str, message: str, next_hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_hint = next_hint


def config_path() -> Path:
    """Single config file. Uses common.config when present (old-home migration), the same fixed path otherwise."""
    try:
        from common.config import config_path as shared_config_path
        return shared_config_path()
    except ImportError:
        return Path.home() / ".projectops" / "config" / "config.json"


def load_config() -> tuple[dict | None, str]:
    """(data, status): status ok | missing | unreadable (missing and broken must differ: never overwrite a broken file)"""
    path = config_path()
    if not path.exists():
        return None, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None, "unreadable"
    return (data, "ok") if isinstance(data, dict) else (None, "unreadable")


def is_secret_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)


def is_valid_credential_name(name: str | None) -> bool:
    return bool(name) and bool(NAME_PATTERN.match(str(name)))


def store_entries(data: dict | None) -> dict:
    """launch.credentials of an already loaded config ({} when absent or malformed)"""
    section = (data or {}).get(STORE_SECTION) if isinstance(data, dict) else None
    entries = section.get(STORE_KEY) if isinstance(section, dict) else None
    return entries if isinstance(entries, dict) else {}


def list_credential_names() -> list[str]:
    data, _status = load_config()
    return sorted(name for name, entry in store_entries(data).items() if isinstance(entry, dict))


def has_credential(name: str) -> bool:
    data, _status = load_config()
    return isinstance(store_entries(data).get(name), dict)


def read_secret(name: str, field: str = "token") -> str:
    """One field of a stored credential, for code only (pass it on via env or stdin, never print it)"""
    data, status = load_config()
    if status == "unreadable":
        raise CredentialError("config_unreadable", "config.json exists but cannot be read")
    entry = store_entries(data).get(name)
    if not isinstance(entry, dict):
        raise CredentialError("cred_not_found", f"No credential named '{name}'",
                              next_hint=f"launch_cli.py cred set --name {name} --secret-field {field} --prompt")
    value = entry.get(field)
    if value in (None, ""):
        raise CredentialError("cred_field_missing", f"'{name}' has no '{field}' value",
                              next_hint=f"launch_cli.py cred set --name {name} --secret-field {field} --prompt")
    return str(value)


def write_config_atomic(data: dict) -> Path:
    """Write the whole config.json with mode 600 (it holds secrets); an interrupted write keeps the old file"""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_path = tempfile.mkstemp(dir=str(path.parent), prefix=".config.", suffix=".tmp")
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2))
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise
    return path


def _load_for_write() -> dict:
    data, status = load_config()
    if status == "unreadable":
        # Overwriting a broken file would wipe every PAT and server entry
        raise CredentialError("config_unreadable", "config.json exists but cannot be read; it was not overwritten")
    return data or {}


def save_secret(name: str, field: str, value: str, metadata: dict | None = None) -> Path:
    """Store one secret field under a name (merge: other fields and sections untouched). metadata = non-secret fields"""
    if not is_valid_credential_name(name):
        raise CredentialError("bad_name", "Name must start with a letter or digit and use only letters, digits and ._-")
    if not value:
        raise CredentialError("value_required", f"Empty value for '{field}'; nothing saved")
    data = _load_for_write()
    entries = data.setdefault(STORE_SECTION, {}).setdefault(STORE_KEY, {})
    entry = dict(entries.get(name) or {})
    for key, metadata_value in (metadata or {}).items():
        entry.setdefault(key, metadata_value)
    entry[field] = value
    entries[name] = entry
    return write_config_atomic(data)


def mask_values(text: str | None, secret_values: list[str]) -> str:
    """Replace leaked secret values in output with *** (values shorter than 4 chars are skipped: too many false hits)"""
    if not text:
        return text or ""
    for secret_value in sorted((str(v) for v in secret_values if v), key=len, reverse=True):
        if len(secret_value) >= 4:
            text = text.replace(secret_value, "***")
    return text


def _is_reference_key(key: str) -> bool:
    return key == REFERENCE_KEY_EXACT or key.endswith(REFERENCE_KEY_SUFFIXES)


def find_credential_references(data: dict | None) -> list[dict]:
    """Every `credential` / `*_cred` / `*_credential` string in config outside the store: [{path, name}]"""
    references: list[dict] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                child_path = f"{path}.{key}" if path else str(key)
                if child_path == f"{STORE_SECTION}.{STORE_KEY}":
                    continue
                if isinstance(child, str) and child and _is_reference_key(str(key)):
                    references.append({"path": child_path, "name": child})
                else:
                    walk(child, child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, f"{path}[{index}]")

    walk(data or {}, "")
    return references


def check_credential_references() -> dict:
    """Read-only check (names and paths only): references to missing entries, entries no section references"""
    data, status = load_config()
    if status == "unreadable":
        raise CredentialError("config_unreadable", "config.json exists but cannot be read")
    references = find_credential_references(data)
    stored_names = set(store_entries(data))
    referenced_names = {reference["name"] for reference in references}
    return {
        "config_status": status,
        "references": references,
        "missing": [reference for reference in references if reference["name"] not in stored_names],
        # Unreferenced is not unused: pro-launch commands also take names directly (--cred)
        "unreferenced": sorted(stored_names - referenced_names),
        "stored_count": len(stored_names),
    }


def plan_github_pat_migration(cred_name: str = GITHUB_PAT_DEFAULT_CRED_NAME) -> dict:
    """What moving github.global_pat into the store would change (no value in the result)"""
    data, status = load_config()
    if status == "unreadable":
        raise CredentialError("config_unreadable", "config.json exists but cannot be read")
    github_section = (data or {}).get("github") if isinstance(data, dict) else None
    github_section = github_section if isinstance(github_section, dict) else {}
    has_global_pat = bool(github_section.get("global_pat"))
    is_name_taken = isinstance(store_entries(data).get(cred_name), dict)
    if not has_global_pat:
        state = "already_migrated" if github_section.get(GITHUB_PAT_REFERENCE_KEY) else "no_global_pat"
    else:
        state = "name_taken" if is_name_taken else "ready"
    return {"state": state, "cred_name": cred_name, "reference_key": f"github.{GITHUB_PAT_REFERENCE_KEY}",
            "changes": ([f"store the PAT as credential '{cred_name}' (field token)",
                         f"set github.{GITHUB_PAT_REFERENCE_KEY} = '{cred_name}'",
                         "remove github.global_pat"] if state == "ready" else [])}


def apply_github_pat_migration(cred_name: str = GITHUB_PAT_DEFAULT_CRED_NAME) -> dict:
    """Move github.global_pat into the store and leave a reference (one write; the old value is not kept anywhere else)"""
    plan = plan_github_pat_migration(cred_name)
    if plan["state"] != "ready":
        return plan
    data = _load_for_write()
    github_section = data["github"]
    entries = data.setdefault(STORE_SECTION, {}).setdefault(STORE_KEY, {})
    entries[cred_name] = {"kind": "token", "provider": "github", "token": github_section["global_pat"],
                          "scope": "repo, workflow",
                          "use_when": "GitHub API calls of every projectops skill (github.global_pat_cred)"}
    github_section[GITHUB_PAT_REFERENCE_KEY] = cred_name
    del github_section["global_pat"]
    write_config_atomic(data)
    return {**plan, "state": "migrated"}
