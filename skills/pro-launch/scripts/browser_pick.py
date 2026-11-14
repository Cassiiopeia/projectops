"""Decide which browser to launch — for places like intranets that cannot download Playwright's bundled Chromium (#857).

Instead of guessing "is this an intranet", decide by **whether a usable browser exists**.
Splitting by IP range or DNS is wrong on VPNs and hotspots. This skill launches the browser as a separate process
and attaches over CDP, so only the executable path changes and the rest runs the same.

Priority
  1. Env var LAUNCH_CHROMIUM_PATH (explicit. A wrong path stops instead of silently moving on)
  2. Playwright bundled Chromium (existing behavior)
  3. Installed Chrome → Edge → Chromium (auto-detected in standard locations)
"""
from __future__ import annotations

import os
import shutil
import socket
import ssl
import sys
from pathlib import Path
from urllib.parse import urlparse

ENV_VAR = "LAUNCH_CHROMIUM_PATH"
DEFAULT_DOWNLOAD_HOST = "https://cdn.playwright.dev"


def system_candidates() -> list[tuple[str, Path]]:
    """Standard locations of installed Chromium-family browsers. Yields (name, path) in order of preference."""
    found: list[tuple[str, Path]] = []
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        for root in filter(None, roots):
            found.append(("Chrome", Path(root) / "Google/Chrome/Application/chrome.exe"))
        for root in filter(None, roots):
            found.append(("Edge", Path(root) / "Microsoft/Edge/Application/msedge.exe"))
    elif sys.platform == "darwin":
        apps = Path("/Applications")
        found += [("Chrome", apps / "Google Chrome.app/Contents/MacOS/Google Chrome"),
                  ("Edge", apps / "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                  ("Chromium", apps / "Chromium.app/Contents/MacOS/Chromium")]
    else:
        for label, names in (("Chrome", ("google-chrome", "google-chrome-stable")),
                             ("Edge", ("microsoft-edge", "microsoft-edge-stable")),
                             ("Chromium", ("chromium", "chromium-browser"))):
            for n in names:
                p = shutil.which(n)
                if p:
                    found.append((label, Path(p)))
    return found


def resolve(bundled: str | None, env: dict | None = None) -> dict:
    """Pick the browser to use.

    Returns: exe (None if none) · source (env|bundled|system) · label · reason · error (only when the env var is wrong)
    """
    env = os.environ if env is None else env
    override = (env.get(ENV_VAR) or "").strip().strip('"')
    if override:
        if Path(override).is_file():
            return {"exe": override, "source": "env", "label": Path(override).stem,
                    "reason": f"set by environment variable {ENV_VAR}"}
        return {"exe": None, "source": "env", "label": ENV_VAR,
                "error": f"The file {ENV_VAR} points to does not exist: {override}",
                "reason": "wrong environment variable path — does not silently fall back to another browser"}
    if bundled and Path(bundled).is_file():
        return {"exe": bundled, "source": "bundled", "label": "Playwright Chromium",
                "reason": "Playwright bundled Chromium"}
    for label, path in system_candidates():
        if path.is_file():
            return {"exe": str(path), "source": "system", "label": label,
                    "reason": f"No bundled Chromium; using the installed browser ({label})"}
    return {"exe": None, "source": None, "label": None,
            "reason": "Found neither bundled Chromium nor an installed Chrome·Edge"}


def download_host() -> str:
    """Where Playwright downloads browsers. People on a corporate mirror already changed it via PLAYWRIGHT_DOWNLOAD_HOST."""
    return (os.environ.get("PLAYWRIGHT_DOWNLOAD_HOST") or DEFAULT_DOWNLOAD_HOST).rstrip("/")


def download_host_reachable(host: str | None = None, timeout: float = 3.0) -> bool:
    """Try up to the TLS handshake and return False if unreachable. Better to know before failing a 100MB download.

    A TCP connect alone is not enough — corporate firewalls accept the connection and drop at the handshake (observed).
    """
    u = urlparse(host or download_host())
    name = u.hostname
    if not name:
        return False
    port = u.port or (443 if u.scheme != "http" else 80)
    try:
        with socket.create_connection((name, port), timeout=timeout) as raw:
            if u.scheme == "http":
                return True
            ctx = ssl.create_default_context()
            ctx.check_hostname = False          # only checks the path is open, not the certificate
            ctx.verify_mode = ssl.CERT_NONE
            raw.settimeout(timeout)
            with ctx.wrap_socket(raw, server_hostname=name):
                return True
    except (OSError, ssl.SSLError):
        return False
