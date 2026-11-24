"""Doctor: resolve destinations > run each adapter's checks > per-destination health, masked command, fix > last-run log
Importable by other skills: run_doctor(context, resolved, target) returns the report; nothing here prints or holds a secret.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import collect, http_client, resolver
from .adapters import adapter_for
from .adapters.base import summarize_checks

LOG_FOLDER_NAME = "pro-brain"
# Last diagnosis per repo: {PROJECTOPS_HOME or ~/.projectops}/pro-brain/doctor/<repo>.json
LOG_SUBFOLDER = "doctor"


def state_folder() -> Path:
    return Path(os.environ.get("PROJECTOPS_HOME") or Path.home() / ".projectops") / LOG_FOLDER_NAME


def log_path(project_key: str) -> Path:
    return state_folder() / LOG_SUBFOLDER / (re.sub(r"[^A-Za-z0-9._-]+", "_", project_key).strip("_") + ".json")


def diagnose_destination(destination: dict, context: dict, quick: bool = False) -> dict:
    """One destination > {id, kind, scope, health, code, checks, command, env, capabilities, fix}"""
    adapter = adapter_for(destination, context)
    try:
        report = adapter.doctor(quick=quick)
    except Exception as error:   # an adapter bug must not hide the other destinations' health
        report = {"checks": [{"name": "adapter", "status": "fail", "code": "adapter_error",
                              "detail": http_client.mask_text(f"{type(error).__name__}: {error}", []),
                              "fix": "report it with /pro-skill-bug"}]}
    health, code = summarize_checks(report["checks"])
    first_fix = next((row.get("fix") for row in report["checks"] if row["status"] == "fail" and row.get("fix")), None)
    shown = {key: destination.get(key) for key in ("name", "mcp_url_shown", "url_origin", "token_cred", "token_cred_origin",
                                                    "write", "role", "origin", "source_id", "path") if destination.get(key)}
    return {"id": destination["id"], "kind": destination["kind"], "scope": destination.get("scope"), **shown,
            "health": health, "code": code, "fix": first_fix, "checks": report["checks"],
            "command": report.get("command"), "env": report.get("env"), "capabilities": report.get("capabilities")}


def scrub(payload: dict) -> dict:
    """Last line of defense before printing or logging: URL userinfo and bearer values masked everywhere"""
    return json.loads(http_client.mask_text(json.dumps(payload, ensure_ascii=False, default=str), []))


def run_doctor(context: dict, resolved: dict, target: str | None = None, quick: bool = False,
               include_read_only: bool = True) -> dict:
    """Doctor for the chosen destinations (default: every configured one, read-only shared brains included)"""
    if target and target != "all":
        chosen, error = resolver.select(resolved, target)
        if error:
            return {"ok": False, "code": "unknown_destination", "summary": error, "destinations": []}
    else:
        chosen = [item for item in resolved["destinations"] if item["is_write_target"] or include_read_only]
    context = {**context, "_resolved": resolved}
    reports = [diagnose_destination(destination, context, quick) for destination in chosen]
    unhealthy = [item for item in reports if item["health"] == "unhealthy" and
                 next((d for d in chosen if d["id"] == item["id"]), {}).get("is_write_target")]
    report = {"ok": not unhealthy, "code": "healthy" if not unhealthy else "unhealthy",
              "checked_at": collect.now_seoul().isoformat(timespec="seconds"),
              "project": context["project"], "destinations": reports,
              "summary": ("; ".join(f"{item['id']}: {item['health']}" + (f" ({item['code']})" if item["code"] else "")
                                    for item in reports) or "no destination configured"),
              "next": (" | ".join(f"{item['id']}: {item['fix']}" for item in unhealthy if item["fix"])
                       or ("write notes with brain_cli.py write --note FILE" if reports else "brain_cli.py setup"))}
    return scrub(report)


def save_log(report: dict, project_key: str) -> str | None:
    """Write the last diagnosis (already scrubbed, no secrets) for later runs and agents; None when not writable"""
    path = log_path(project_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)
    except OSError:
        return None


def read_last(project_key: str) -> dict | None:
    try:
        return json.loads(log_path(project_key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
