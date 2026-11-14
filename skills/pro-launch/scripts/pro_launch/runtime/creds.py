"""Thin layer for commands to use stored credentials. Storage and masking themselves are in credentials.py."""
from __future__ import annotations


import credentials


#
# Same approach pro-ssh · pro-github use with servers and PATs in config.json.
# Secrets live only in config.json in the user home (launch.credentials); access.json holds only the name.
def load_cred(name: str | None):
    """(credential, None) or (None, payload for the error JSON)."""
    if not name:
        return None, None
    try:
        return credentials.resolve(name), None
    except credentials.CredError as e:
        return None, {"ok": False, "code": e.code, "error": e.message,
                      "next": "cred list  # shows saved credentials and their use_when"}


def cred_name_for(args, saved) -> str | None:
    """Without --cred, use the cred name written in the access record."""
    if getattr(args, "cred", None):
        return args.cred
    return saved.get("cred") if isinstance(saved, dict) else None


def cred_field(name: str, field: str | None) -> tuple[str | None, dict | None]:
    """Take one value to type from a stored credential (default password). (value, None) or (None, error)."""
    cred, err = load_cred(name)
    if err:
        return None, err
    f = field or "password"
    v = cred.get(f)
    if v in (None, ""):
        # Show only typeable values (text·numbers) as choices — objects like login_policy are excluded
        keys = sorted(k for k, x in cred.items() if isinstance(x, (str, int, float)) and x != ""
                      and k not in ("name", "kind"))
        return None, {"ok": False, "code": "cred_field_missing",
                      "error": f"'{name}' has no '{f}' value", "fields": keys,
                      "next": f"cred set --name {name} --json '{{\"{f}\": \"...\"}}'  # or pick another field with --cred-field"}
    return str(v), None


def with_login_policy(payload: dict, cred_name: str | None) -> dict:
    """Attach the final policy to the login input result (#905). Only on success and user handoff (needs_user); other failures as is

    The agent uses this to decide whether to handle sign-in interstitials (trust device · stay signed in · prompts) without asking.
    """
    if payload.get("ok") is False and payload.get("code") != "needs_user":
        return payload
    try:
        payload["login_policy"] = credentials.resolve_login_policy(cred_name)
    except Exception:
        pass                                        # the input result is emitted even if the policy cannot be read
    return payload
