"""Paseo adapter (relay, no tunnel): find the bundled CLI > daemon and relay check > fresh pairing link from `daemon pair`
Read-only on the daemon: never restarts it, changes its listen address or turns on the web UI. Facts in harness/paseo.md
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

NAME = "paseo"
CONNECTION = "relay"
# Env override for an install folder the candidates below miss (full path to the paseo executable)
CLI_OVERRIDE_ENV = "PROJECTOPS_PASEO_CLI"
# Daemon CLI calls can wait on the daemon (status alone has a 1.5 s inner timeout)
CLI_TIMEOUT_SECONDS = 30
# Pairing link shape: https://app.paseo.sh/#offer=<base64url>
OFFER_LINK_PATTERN = re.compile(r"https://[^\s\"']+#offer=[A-Za-z0-9_\-=%.]+")
# Relay off: the agent asks the user; enabling is `daemon pair --relay`
RELAY_OFF_NEXT = "ask the user whether to turn on the Paseo relay; if yes, run `link get --app paseo --enable-relay`"


def _bundled_cli_candidates() -> list[Path]:
    """CLI shipped inside the desktop app, per OS (harness/paseo.md 'Where the CLI is')"""
    if sys.platform == "darwin":
        return [Path("/Applications/Paseo.app/Contents/Resources/bin/paseo"),
                Path.home() / "Applications/Paseo.app/Contents/Resources/bin/paseo"]
    if sys.platform.startswith("win"):
        roots = [os.environ.get("ProgramFiles") or r"C:\Program Files",
                 str(Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "Programs")]
        return [Path(root) / "Paseo" / "resources" / "bin" / "paseo.cmd" for root in roots]
    return [Path("/opt/Paseo/resources/bin/paseo")]


def find_cli() -> str | None:
    """Paseo CLI path: env override > PATH > app bundle"""
    override = os.environ.get(CLI_OVERRIDE_ENV, "").strip()
    if override and Path(override).is_file():
        return override
    on_path = shutil.which("paseo")
    if on_path:
        return on_path
    return next((str(path) for path in _bundled_cli_candidates() if path.is_file()), None)


def _run(cli: str, arguments: list[str]) -> tuple[int | None, str, str]:
    """(exit code, stdout, stderr). cwd is home: a cwd under a protected folder (macOS ~/Desktop) crashes the CLI with uv_cwd EPERM"""
    try:
        completed = subprocess.run([cli, *arguments], capture_output=True, stdin=subprocess.DEVNULL,
                                   cwd=str(Path.home()), timeout=CLI_TIMEOUT_SECONDS,
                                   encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as error:
        return None, "", f"{type(error).__name__}: {error}"
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _run_json(cli: str, arguments: list[str]) -> dict | None:
    code, stdout, _stderr = _run(cli, arguments)
    if code != 0:
        return None
    try:
        parsed = json.loads(stdout)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _config_value(cli: str, path: str) -> tuple[bool, object]:
    """(read ok, value) of `daemon config get <path>`; value None when the key is not set"""
    answer = _run_json(cli, ["daemon", "config", "get", path])
    if answer is None:
        return False, None
    return True, answer.get("value") if answer.get("set") else None


def _has_password(cli: str) -> bool | None:
    """Daemon password hash present in config.json (daemon.auth.password). None if config could not be read
    Only presence is read; the hash never leaves this function"""
    is_read, auth = _config_value(cli, "daemon.auth")
    if not is_read:
        return None
    return isinstance(auth, dict) and bool(auth.get("password"))


def mask_link(text: str) -> str:
    """Hide the offer part of pairing links (for error text and logs)"""
    return re.sub(r"#offer=[^\s\"']+", "#offer=<hidden>", text)


def inspect() -> dict:
    """CLI found > daemon running > relay on > password set. Reachable from outside = running and relay on"""
    cli = find_cli()
    if not cli:
        return {"is_installed": False, "is_running": False, "is_reachable": False, "cli": None,
                "next": "Paseo CLI not found: see harness/paseo.md 'Where the CLI is'"}
    status = _run_json(cli, ["daemon", "status", "--json"]) or {}
    is_running = status.get("localDaemon") == "running"
    _is_read, relay = _config_value(cli, "daemon.relay")
    is_relay_enabled = isinstance(relay, dict) and relay.get("enabled") is True
    has_password = _has_password(cli)
    if not is_running:
        next_step = "start Paseo desktop (harness/paseo.md 'If Paseo is not running')"
    elif not is_relay_enabled:
        next_step = "relay is off: ask the user before `link get --app paseo --enable-relay`"
    else:
        next_step = "link get --app paseo"
    return {"is_installed": True, "cli": cli, "is_running": is_running,
            "listen": status.get("listen"), "is_desktop_managed": status.get("desktopManaged"),
            "daemon_version": status.get("daemonVersion"), "is_relay_enabled": is_relay_enabled,
            "has_password": has_password, "is_reachable": is_running and is_relay_enabled, "next": next_step}


def _password_warning(has_password: bool | None) -> dict:
    if has_password:
        return {}
    if has_password is None:
        return {"warning": "could not read daemon.auth from the Paseo config; password state unknown"}
    return {"warning": "no daemon password in the Paseo config: anyone holding this link can connect",
            "warning_fix": "the user can run `paseo daemon set-password` on the computer (then the daemon needs a restart: ask first)"}


def fresh_link(should_enable_relay: bool = False) -> dict:
    """New pairing link from `daemon pair --json`. Relay off and not allowed > relay_off (never enabled silently)"""
    facts = inspect()
    if not facts["is_installed"]:
        return {"ok": False, "code": "tool_missing", "summary": "Paseo CLI not found", "next": facts["next"]}
    if not facts["is_running"]:
        return {"ok": False, "code": "app_not_running", "summary": "the Paseo daemon is not running",
                "next": facts["next"], "cli": facts["cli"]}
    if not facts["is_relay_enabled"] and not should_enable_relay:
        return {"ok": False, "code": "relay_off", "summary": "Paseo relay is off, so a link would not work from outside",
                "next": RELAY_OFF_NEXT}
    arguments = ["daemon", "pair", "--json", *(["--relay"] if should_enable_relay else [])]
    code, stdout, stderr = _run(facts["cli"], arguments)
    try:
        answer = json.loads(stdout) if code == 0 else {}
    except ValueError:
        answer = {}
    link = answer.get("url") if isinstance(answer, dict) else None
    if not link:
        match = OFFER_LINK_PATTERN.search(stdout)
        link = match.group(0) if match else None
    if not link or "#offer=" not in link:
        return {"ok": False, "code": "pair_failed", "exit_code": code,
                "summary": "`paseo daemon pair --json` gave no #offer= link",
                "stderr": mask_link(stderr.strip())[-400:],
                "next": "read harness/paseo.md 'The link the user opens'; the CLI output shape may have changed"}
    if answer.get("relayEnabled") is False:
        return {"ok": False, "code": "relay_off", "summary": "pairing link made without relay, so it would not work from outside",
                "next": RELAY_OFF_NEXT}
    return {"app": NAME, "link": link, "has_password": facts["has_password"], **_password_warning(facts["has_password"]),
            "summary": "fresh Paseo pairing link (relay)"}
