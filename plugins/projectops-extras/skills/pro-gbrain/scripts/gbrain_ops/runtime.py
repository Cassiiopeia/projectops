"""GBrain runner: executable lookup, secret-free environment, JSON decoding and output redaction"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import common, credentials


def executable(env: dict | None = None) -> str | None:
    env = env or common.gbrain_environment()
    explicit = env.get("PRO_BRAIN_GBRAIN")
    return shutil.which(explicit or "gbrain", path=env.get("PATH"))


def redact(value, secrets=()):
    if isinstance(value, dict):
        # Mask only string values under secret-looking keys; counts such as newTokens stay readable
        return {key: ("<secret>" if isinstance(item, str) and credentials.is_secret_key(key)
                      and not key.endswith(("_source", "_cred", "_path"))
                      else redact(item, secrets)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "<secret>")
        value = re.sub(r"(https?|postgres(?:ql)?)://[^\s/@]+:[^\s/@]+@", r"\1://<secret>@", value)
        value = re.sub(r"(?i)([?&](?:token|key|secret|password)=)[^&\s]+", r"\1<secret>", value)
        value = re.sub(r"(?i)(bearer\s+)[\w.\-]+", r"\1<secret>", value)
    return value


def decode(text: str):
    # setup prints a target description before its JSON: decode the trailing JSON value
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", text):
        try:
            value, end = decoder.raw_decode(text[match.start():])
            if not text[match.start() + end:].strip():
                return value
        except ValueError:
            continue
    return None


def environment(args) -> tuple[dict, list[str]]:
    home = getattr(args, "gbrain_home", None)
    env = common.gbrain_environment(Path(home).expanduser().resolve() if home else None)
    if home:
        # A separate brain home also isolates harness wiring; otherwise setup rewires the real ~/.codex and ~/.claude
        isolated = Path(home).expanduser().resolve()
        env["CODEX_HOME"] = str(isolated / ".codex")
        env["CLAUDE_CONFIG_DIR"] = str(isolated / ".claude")
    secrets = []
    cred = getattr(args, "credential", None)
    if cred:
        field = getattr(args, "credential_field", None) or "token"
        name = getattr(args, "credential_env", None)
        if name not in {"OPENAI_API_KEY", "VOYAGE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "GBRAIN_DATABASE_URL"}:
            raise common.StepError("credential_env_required", "choose a supported provider or database environment variable",
                                   "pass --credential-env and --credential-field; never pass the secret itself")
        secret = credentials.read_secret(cred, field)
        env[name] = secret
        secrets.append(secret)
    return env, secrets


def incomplete(value) -> bool:
    if isinstance(value, list):
        return any(incomplete(item) for item in value)
    if not isinstance(value, dict):
        return False
    if value.get("ok") is False or value.get("error"):
        return True
    if value.get("outcome") in {"blocked", "resumable"} or value.get("status") in {"error", "failed", "blocked"}:
        return True
    if isinstance(value.get("error_count"), int) and value["error_count"] > 0:
        return True
    return any(incomplete(value[key]) for key in ("sources", "results") if key in value)


def run(arguments: list[str], args=None, timeout=90, env=None) -> dict:
    secrets = []
    if env is None:
        env, secrets = environment(args)
    binary = executable(env)
    if binary is None:
        return {"ok": False, "code": "gbrain_missing", "summary": "GBrain is not installed or executable",
                "next": "manage install"}
    try:
        completed = subprocess.run([binary, *arguments], env=env, capture_output=True, encoding="utf-8",
                                   errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "gbrain_timeout", "summary": "GBrain exceeded the operation timeout",
                "next": "inspect manage doctor and the source status before retrying"}
    except OSError as error:
        return {"ok": False, "code": "gbrain_exec_failed", "summary": str(error), "next": "manage doctor"}
    parsed = decode(completed.stdout or "")
    # A structured failure stays a failure even with exit code 0
    failed = incomplete(parsed)
    result = {"ok": completed.returncode == 0 and not failed, "exit_code": completed.returncode,
              "code": "executed" if completed.returncode == 0 and not failed else "gbrain_failed",
              "result": parsed, "next": None}
    if parsed is None:
        result["output"] = (completed.stdout or "")[-8000:]
    if completed.stderr:
        result["diagnostics"] = completed.stderr[-2000:]
    if not result["ok"]:
        # GBrain refusals carry the exact fix in `suggestion`; pass it on instead of a generic hint
        result["next"] = (parsed.get("next") or parsed.get("suggestion")) if isinstance(parsed, dict) else "manage doctor"
        missing = ((parsed.get("diagnosis") or {}).get("missingEnvVars") or []) if isinstance(parsed, dict) else []
        if missing:
            # Provider key absent: name the variable to fill from a stored credential
            result["next"] = (f"store the provider key, then repeat with --credential NAME --credential-field api_key "
                              f"--credential-env {missing[0]}")
        result["next"] = result["next"] or "manage doctor"
    return redact(result, secrets)


def supports(command: str, args=None) -> bool:
    result = run(["--help"], args)
    return result["ok"] and bool(re.search(r"(?m)^\s+" + re.escape(command) + r"(?:\s|$)", result.get("output", "")))


def engine(args=None) -> dict:
    result = run(["engine", "status", "--json"], args)
    data = result.get("result") or {}
    if not isinstance(data, dict):
        data = {}
    return {"ok": result["ok"], "code": result["code"],
            **{key: data.get(key) for key in ("brain_id", "effective_engine", "db_url_source", "thin_client")},
            "connection": "not_probed", "next": result.get("next")}


def require_stored_credential(args) -> None:
    """Refuse a plan whose --credential name is not in the store (presence only, the value is not read)"""
    name = getattr(args, "credential", None)
    if name and name not in credentials.list_credential_names():
        raise common.StepError("credential_missing", f"no stored credential named {name}",
                               "store it with hidden input: projectops_cli.py launch cred set --name NAME --prompt")


def plan_or_run(argv: list[str], args, *, effects: list[str], timeout=600) -> dict:
    require_stored_credential(args)
    plan = {"ok": True, "code": "plan", "argv": ["gbrain", *argv], "effects": effects,
            "gbrain_home": getattr(args, "gbrain_home", None), "summary": "review the selected target and effects",
            "next": "repeat this command with --apply --yes"}
    if not getattr(args, "apply", False):
        return plan
    if not getattr(args, "yes", False):
        raise common.StepError("needs_consent", "applying this plan requires --yes", plan["next"])
    return {**run(argv, args, timeout=timeout), "effects": effects}
