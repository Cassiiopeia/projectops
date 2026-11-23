"""Named credential store (pro-launch). Other skills read it through common/credentials.py (config-rules.md §9).

Same approach pro-ssh · pro-github use with servers and PATs in `~/.projectops/config/config.json`.
pro-launch keeps them in the `launch` section of the same file **so the next run does not ask again**.

    config["launch"]["credentials"][name] = {
        "kind": "ssh | dockerhub | db | http | github-org | token | other",
        "use_when": "grounds for the agent to decide whether it may use this credential",
        "scope": "test-only | readonly | ...   (what is allowed)",
        "notes": "things to know (port range, naming rules to keep, production services on the server, etc.)",
        "ssh_server": "server name registered in pro-ssh — if set, host·port·user·password come from there",
        ... values (password · token · username · host ...)
    }

**Why config.json and not access.json**: access.json records per-project "how to connect" and
must hold no secrets (find_secrets blocks them). Secrets live only in this one file in the user home.
access.json holds only the name, like `{"cred": "name"}`.
"""
from __future__ import annotations

from pathlib import Path

from common import config as cfg
from common import credentials as credential_store

# Name rule and secret field markers: one source in common/credentials.py (config-rules.md §9)
NAME_RE = credential_store.NAME_PATTERN
SECRET_KEYS = credential_store.SECRET_KEY_MARKERS


class CredError(Exception):
    """Save or lookup failure. code becomes the code of the JSON response."""

    def __init__(self, code: str, message: str, next_hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_hint = next_hint                  # next of the JSON response (only when present)


def _is_secret_key(key: str) -> bool:
    return credential_store.is_secret_key(key)


def _section(data: dict | None, create: bool = False) -> dict:
    data = data if isinstance(data, dict) else {}
    launch = data.get("launch")
    if not isinstance(launch, dict):
        if not create:
            return {}
        launch = data["launch"] = {}
    creds = launch.get("credentials")
    if not isinstance(creds, dict):
        if not create:
            return {}
        creds = launch["credentials"] = {}
    return creds


def load_all() -> dict:
    return _section(cfg.load())


def ssh_servers() -> list[dict]:
    """Server list of the old pro-ssh `ssh` section in config.json (read-only)."""
    data = cfg.load() or {}
    servers = data.get("ssh")
    if isinstance(servers, dict):                 # old shape {"instances": [...]}
        servers = servers.get("instances")
    return [s for s in servers or [] if isinstance(s, dict)]


def _ssh_server(name: str) -> dict | None:
    for s in ssh_servers():
        if s.get("name") == name:
            return s
    return None


def resolve(name: str) -> dict:
    """Look up a credential by name. With an `ssh_server` reference, merge onto the pro-ssh server values."""
    entry = load_all().get(name)
    if not isinstance(entry, dict):
        known = ", ".join(sorted(load_all())) or "(none)"
        raise CredError("cred_not_found", f"No credential named '{name}'. Available: {known}")
    merged: dict = {}
    ref = entry.get("ssh_server")
    if ref:
        srv = _ssh_server(ref)
        if not srv:
            raise CredError("ssh_server_not_found", f"pro-ssh has no server '{ref}'")
        for k in ("host", "port", "user", "password", "key_path", "auth"):
            if srv.get(k) not in (None, ""):
                merged[k] = srv[k]
    merged.update({k: v for k, v in entry.items() if v not in (None, "")})
    merged["name"] = name
    return merged


def public_view(entry: dict, reveal: bool = False) -> dict:
    """Shape shown to people and agents. Secret values are masked as `<saved>`."""
    if reveal:
        return dict(entry)
    return {k: ("<saved>" if (_is_secret_key(k) and v) else v) for k, v in entry.items()}


def secret_values(entry: dict) -> list[str]:
    return [str(v) for k, v in entry.items() if _is_secret_key(k) and isinstance(v, (str, int)) and str(v)]


def mask(text: str | None, entry: dict) -> str:
    """Mask secret values that leaked into output (e.g. a server echoing env vars)."""
    if not text:
        return text or ""
    for v in sorted(secret_values(entry), key=len, reverse=True):
        if len(v) >= 4:
            text = text.replace(v, "***")
    return text


def env_for(entry: dict) -> dict:
    """Let the command read stored values as env vars, so secrets need not be in the command string."""
    env = {"CRED_NAME": entry.get("name", ""), "CRED_KIND": str(entry.get("kind", ""))}
    mapping = {"host": "CRED_HOST", "port": "CRED_PORT", "user": "CRED_USER", "username": "CRED_USERNAME",
               "password": "CRED_PASSWORD", "token": "CRED_TOKEN", "db": "CRED_DB"}
    for k, var in mapping.items():
        if entry.get(k) not in (None, ""):
            env[var] = str(entry[k])
    if entry.get("password"):
        env["SSHPASS"] = str(entry["password"])      # read by sshpass -e
    return env


def validate_name(name: str | None) -> str:
    if not name or not NAME_RE.match(name):
        raise CredError("bad_name", "--name must start with a letter or digit and use only letters, digits and ._- (64 chars max)")
    return name


def _write_config(data: dict) -> Path:
    """Write config.json (mode 600, atomic) through the shared accessor"""
    return credential_store.write_config_atomic(data)


def save_credential(name: str, fields: dict, replace: bool = False) -> Path:
    """Update only launch.credentials[name] without touching other sections (github · ssh ...)."""
    validate_name(name)
    if not isinstance(fields, dict) or not fields:
        raise CredError("value_required", "--json must be a non-empty JSON object")
    data = cfg.load()
    if data is None and cfg.config_path().exists():
        # File exists but cannot be read = broken. Overwriting would wipe all PAT and server info.
        raise CredError("config_unreadable", "Could not read config.json (it may be corrupted). It was not overwritten")
    if "login_policy" in fields:
        # Policy needs key/value validation and per-key merge > only through its own path (#905)
        raise CredError("use_cred_policy", "login_policy is not changed with cred set",
                        next_hint=f"cred policy set --name {name} --key <key> --value <ask|always|never>")
    data = data or {}
    creds = _section(data, create=True)
    existing = dict(creds.get(name) or {})
    base = {} if replace else existing
    base.update(fields)
    if replace and isinstance(existing.get("login_policy"), dict):
        base["login_policy"] = existing["login_policy"]   # --replace changes values only. Policy goes through cred policy unset
    creds[name] = base
    return _write_config(data)


def delete_credential(name: str) -> bool:
    data = cfg.load()
    creds = _section(data)
    if name not in creds:
        return False
    del creds[name]
    _write_config(data)
    return True


# ── Login interstitial policy (#905) ─────────────────────────────────────────
# Resolution: account launch.credentials.<name>.login_policy > global launch.login_policy > ask
# 3 screens: trust device (don't ask again) · stay signed in · prompts like adding a passkey or contact
LOGIN_POLICY_KEYS = ("trust_device", "keep_signed_in", "skip_nags")
# ask: ask the user · always: accept without asking (prompts are skipped) · never: decline without asking
LOGIN_POLICY_VALUES = ("ask", "always", "never")
LOGIN_POLICY_DEFAULT_VALUE = "ask"


def _validate_login_policy(key: str, value: str | None = None) -> None:
    if key not in LOGIN_POLICY_KEYS:
        raise CredError("invalid_policy_key", f"'{key}' is not a policy key. Allowed: {', '.join(LOGIN_POLICY_KEYS)}")
    if value is not None and value not in LOGIN_POLICY_VALUES:
        raise CredError("invalid_policy_value", f"'{value}' is not a policy value. Allowed: {', '.join(LOGIN_POLICY_VALUES)}")


def _policy_of(holder) -> dict:
    """Keep only valid keys and values from a login_policy object (hand-edited bad values count as absent)"""
    policy = holder.get("login_policy") if isinstance(holder, dict) else None
    if not isinstance(policy, dict):
        return {}
    return {key: value for key, value in policy.items() if key in LOGIN_POLICY_KEYS and value in LOGIN_POLICY_VALUES}


def resolve_login_policy(name: str | None) -> dict:
    """Final policy: per key {"value", "source": credential | global | default}"""
    data = cfg.load()
    data = data if isinstance(data, dict) else {}       # unreadable or not an object: no saved choice
    launch = data.get("launch") if isinstance(data.get("launch"), dict) else {}
    global_policy = _policy_of(launch)
    credential_policy = _policy_of(_section(data).get(name)) if name else {}
    resolved = {}
    for key in LOGIN_POLICY_KEYS:
        if key in credential_policy:
            resolved[key] = {"value": credential_policy[key], "source": "credential"}
        elif key in global_policy:
            resolved[key] = {"value": global_policy[key], "source": "global"}
        else:
            resolved[key] = {"value": LOGIN_POLICY_DEFAULT_VALUE, "source": "default"}
    return resolved


def _load_for_policy_write() -> dict:
    """Read the config to write the policy into. Broken files are not overwritten (protects PAT and server info)"""
    data = cfg.load()
    if (data is None and cfg.config_path().exists()) or (data is not None and not isinstance(data, dict)):
        raise CredError("config_unreadable", "Could not read config.json (it may be corrupted). It was not overwritten")
    return data or {}


def _policy_holder(data: dict, name: str | None, create: bool) -> dict | None:
    """Object to hold the policy: the account if named, otherwise the launch section. cred_not_found if the account is missing"""
    if name:
        entry = _section(data).get(name)
        if not isinstance(entry, dict):
            known = ", ".join(sorted(_section(data))) or "(none)"
            raise CredError("cred_not_found", f"No credential named '{name}'. Available: {known}")
        return entry
    launch = data.get("launch")
    if not isinstance(launch, dict):
        if not create:
            return None
        launch = data["launch"] = {}
    return launch


def has_credential(name: str) -> bool:
    """Only checks whether the named entry exists (ssh_server references are not resolved)"""
    return isinstance(load_all().get(name), dict)


def set_login_policy(name: str | None, key: str, value: str) -> Path:
    """Save one policy key — on the account if named, otherwise as the global default"""
    _validate_login_policy(key, value)
    data = _load_for_policy_write()
    holder = _policy_holder(data, name, create=True)
    policy = holder.get("login_policy") if isinstance(holder.get("login_policy"), dict) else {}
    policy[key] = value
    holder["login_policy"] = policy
    return _write_config(data)


def unset_login_policy(name: str | None, key: str) -> bool:
    """Remove one policy key (falls back to the layer above). Removes the login_policy object when it was the last key. True if removed"""
    _validate_login_policy(key)
    data = _load_for_policy_write()
    holder = _policy_holder(data, name, create=False)
    policy = holder.get("login_policy") if holder else None
    if not isinstance(policy, dict) or key not in policy:
        return False
    del policy[key]
    if not policy:
        del holder["login_policy"]
    _write_config(data)
    return True
