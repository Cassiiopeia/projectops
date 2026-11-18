"""Ego Lite engine for `web signin`: availability, engine choice, hand-over block (#1231).

Pure logic. Every outside call (finding the command, the display check, the probe) is injectable so it is testable
without Ego Lite installed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EGO_BROWSER_COMMAND_NAME = "ego-browser"
# The ego lite onboarding registers the command here when PATH does not have it
EGO_BROWSER_FALLBACK_PATH = Path.home() / ".local" / "bin" / EGO_BROWSER_COMMAND_NAME
# Time limit for the readiness probe (seconds)
EGO_PROBE_TIMEOUT_SECONDS = 20
EGO_PROBE_READY_TEXT = "ego-browser ready"
# Fields handed to the agent, in this order. Notes and every other credential field stay out
HANDOFF_FIELD_NAMES = ("provider", "account", "password", "second_factor", "login_policy")
# Same names `web login` accepts for the user id (commands/web/actions/login.py); the first one with a value is handed over as `account`
IDENTIFIER_FIELD_CANDIDATES = ("username", "account", "email", "user", "login", "id")


@dataclass(frozen=True)
class EgoAvailability:
    """is_available: probe passed. reason: ready | ego_not_found | ego_not_onboarded | ego_no_display | ego_probe_timeout"""
    is_available: bool
    reason: str
    command: str | None


@dataclass(frozen=True)
class EngineDecision:
    """engine: ego | legacy | unavailable (a forced ego that cannot run)."""
    engine: str
    reason: str


def find_ego_browser_command() -> str | None:
    """Path of the ego-browser command: PATH first, then ~/.local/bin."""
    on_path = shutil.which(EGO_BROWSER_COMMAND_NAME)
    if on_path:
        return on_path
    if EGO_BROWSER_FALLBACK_PATH.is_file() and os.access(EGO_BROWSER_FALLBACK_PATH, os.X_OK):
        return str(EGO_BROWSER_FALLBACK_PATH)
    return None


def has_display() -> bool:
    """macOS and Windows always have one; Linux needs a display variable (servers and CI do not)."""
    if sys.platform in ("darwin", "win32"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def check_ego_availability(find_command=find_ego_browser_command, check_display=has_display,
                           run_probe=subprocess.run) -> EgoAvailability:
    """Command found > display present > probe answers ready. An app without finished onboarding answers with a setup window and a non-ready result."""
    command = find_command()
    if not command:
        return EgoAvailability(False, "ego_not_found", None)
    if not check_display():
        return EgoAvailability(False, "ego_no_display", command)
    try:
        result = run_probe([command, "nodejs", "-e", f"console.log('{EGO_PROBE_READY_TEXT}')"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=EGO_PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return EgoAvailability(False, "ego_probe_timeout", command)
    except OSError:
        return EgoAvailability(False, "ego_not_found", command)
    # ego-browser prints the script's console.log output to stderr, so both streams are checked
    probe_output = f"{result.stdout or ''}{result.stderr or ''}"
    is_ready = result.returncode == 0 and EGO_PROBE_READY_TEXT in probe_output
    return EgoAvailability(is_ready, "ready" if is_ready else "ego_not_onboarded", command)


def decide_engine(requested: str, availability: EgoAvailability, has_signed_in_current_profile: bool) -> EngineDecision:
    """auto: stay on the current engine when its profile is already signed in, else Ego Lite when available. ego: Ego Lite or unavailable. legacy: always current."""
    if requested == "legacy":
        return EngineDecision("legacy", "requested")
    if requested == "ego":
        if availability.is_available:
            return EngineDecision("ego", "requested")
        return EngineDecision("unavailable", availability.reason)
    if requested != "auto":
        raise ValueError(f"engine must be auto, ego or legacy: {requested!r}")
    if has_signed_in_current_profile:
        return EngineDecision("legacy", "signed_in_profile")
    if availability.is_available:
        return EngineDecision("ego", availability.reason)
    return EngineDecision("legacy", availability.reason)


def build_signin_handoff(credential: dict, login_policy: dict) -> tuple[dict | None, dict | None]:
    """(hand-over block, None), or (None, cred_field_missing payload) when account or password is empty."""
    account = next((credential[field] for field in IDENTIFIER_FIELD_CANDIDATES if credential.get(field) not in (None, "")), None)
    missing = [field for field, value in (("account", account), ("password", credential.get("password"))) if not value]
    if missing:
        name = credential.get("name") or "<name>"
        return None, {"ok": False, "code": "cred_field_missing",
                      "error": f"'{name}' has no '{missing[0]}' value", "fields": missing,
                      "next": f"cred set --name {name} --json '{{\"{missing[0]}\": \"...\"}}'"}
    return {
        "provider": credential.get("provider"),
        "account": account,
        "password": credential["password"],
        "second_factor": credential.get("two_factor"),
        "login_policy": login_policy,
    }, None
