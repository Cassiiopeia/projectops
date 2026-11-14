"""Shared helpers for `desktop` actions: setup, window picking, screen comparison, capture saving (#985)."""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

from common.state import venv_site_packages

import desktop_input

from pro_launch.runtime.context import project_root
from pro_launch.runtime.creds import cred_field
from pro_launch.runtime.mutating import is_mutating_label
from pro_launch.runtime.output import set_target
from pro_launch.runtime.shots import finish_shot, shot_target

# --window reserved word: system dialogs and notification banners rather than the front window (macOS)
OVERLAY_QUERY = "overlay"
OVERLAY_ORDER = ("dialog", "notification")
# Kinds excluded from the danger check — notification banners only open
DESKTOP_NAV_ROLES = {"notification"}
# Interval (s) after which the screen counts as settled, and max wait (s)
SETTLE_INTERVAL_SECONDS = 0.25
SETTLE_MAX_SECONDS = 3.0


def load_backend() -> tuple[desktop_input.DesktopBackend | None, dict | None]:
    """(backend, failure result). Adds the shared venv site-packages, then checks dependencies."""
    site = venv_site_packages()
    if site and str(site) not in sys.path:
        sys.path.insert(0, str(site))
    key = desktop_input.platform_key()
    if key not in desktop_input.BACKENDS:
        return None, {"ok": False, "code": "unsupported_on_platform",
                      "error": f"desktop control supports {', '.join(desktop_input.BACKENDS)} for now, not {sys.platform}"}
    try:
        be = desktop_input.get_backend(key)
    except Exception as e:   # noqa: BLE001 — the backend module failed to import an OS library
        return None, deps_missing(key, [type(e).__name__ + ": " + str(e)[:200]])
    missing = be.missing_modules()
    if missing:
        return None, deps_missing(key, missing, be)
    return be, None


def deps_missing(key: str, missing: list[str], be=None) -> dict:
    packages = " ".join(be.packages) if be else "(see desktop setup)"
    return {"ok": False, "code": "desktop_deps_missing", "platform": key, "missing": missing,
            "error": f"desktop control needs {', '.join(missing)}",
            "fix": "desktop setup", "manual": f"pip install {packages}",
            "next": "desktop setup  # installs into the shared venv (ask the user first)"}


def target_window(window: dict | None) -> dict | None:
    """Window this command handles — attaches the harness (guide) matching its title / program name to the response (projectops#1024)."""
    if window:
        set_target(window=[window.get("title"), window.get("app")], area="desktop")
    return window


def pick_window(be, query: str | None) -> tuple[dict | None, dict | None]:
    """--window (part of title, pid, handle, overlay) or the front window. (window, failure result)"""
    window, failure = _pick_window(be, query)
    return target_window(window), failure


def _pick_window(be, query: str | None) -> tuple[dict | None, dict | None]:
    wins = be.windows()
    if not wins:
        return None, {"ok": False, "code": "window_not_found", "error": "No visible windows"}
    if query == OVERLAY_QUERY:
        return _pick_overlay(wins)
    if not query:
        front = next((w for w in wins if w["foreground"]), None)
        if front:
            return front, None
        return None, {"ok": False, "code": "window_not_found", "error": "No window is in front",
                      "candidates": [w["title"] for w in wins[:15]],
                      "next": "desktop windows  # then pass --window"}
    if query.isdigit():
        n = int(query)
        hit = next((w for w in wins if n in (w["handle"], w["pid"])), None)
        if hit:
            return hit, None
    lowered = query.lower()
    hits = [w for w in wins if lowered in w["title"].lower() or lowered == (w.get("app") or "").lower()]
    if hits:
        return hits[0], None
    return None, {"ok": False, "code": "window_not_found", "error": f"No window matches {query!r}",
                  "candidates": [w["title"] for w in wins[:15]],
                  "next": "desktop windows  # pick a title from candidates"}


def ordered_overlays(wins: list[dict]) -> list[dict]:
    """System dialogs (2FA, permission popups) > notification banners. Selectable without knowing the owning process."""
    return [w for kind in OVERLAY_ORDER for w in wins if w.get("overlay") and w.get("overlay_kind") == kind]


def _pick_overlay(wins: list[dict]) -> tuple[dict | None, dict | None]:
    found = ordered_overlays(wins)
    if found:
        return found[0], None
    return None, {"ok": False, "code": "window_not_found", "error": "No system dialog or notification is on screen",
                  "next": "desktop windows"}


def windows_to_search(be, query: str | None) -> tuple[list[dict], dict | None]:
    """Windows that text-based actions (find, wait) scan. overlay means all — so banners are found even with a dialog open."""
    if query == OVERLAY_QUERY:
        found = ordered_overlays(be.windows())
        if found:
            target_window(found[0])
        return (found, None) if found else ([], _pick_overlay([])[1])
    window, failure = pick_window(be, query)
    return ([window] if window else []), failure


def public_window(w: dict) -> dict:
    return {k: w[k] for k in ("handle", "pid", "app", "title", "bounds", "foreground", "minimized", "elevated",
                              "overlay", "overlay_kind") if k in w}


def listed_nodes(nodes: list[dict]) -> list[dict]:
    """Pick only nodes to show and flag dangerous buttons (desktop also blocks install/consent/allow kinds)
    Notification banners are excluded — their text is the body and pressing only opens. Hidden buttons are judged by name via `click --action`"""
    shown = [n for n in nodes if desktop_input.is_worth_listing(n)]
    for n in shown:
        n["mutating"] = (n["clickable"] and n["role"] not in DESKTOP_NAV_ROLES
                         and is_mutating_label(f"{n['text']} {n['desc']}", is_desktop=True))
    return shown


def compare_region(window: dict, node: dict) -> list[int]:
    """Area to watch for changes after a press. Notification Center spans the whole screen, so only the banner area (keeps other apps' changes out)."""
    if window.get("overlay_kind") == "notification" and node.get("bounds"):
        return node["bounds"]
    return window["bounds"]


def screen_digest(be, region: list[int] | None) -> str | None:
    png = be.grab(region)
    return hashlib.sha1(png).hexdigest() if png else None


def settle(be, region: list[int] | None, before: str | None) -> tuple[bool | None, float]:
    """Wait until the screen changes and settles. (changed, seconds waited). (None, 0) if capture fails."""
    if before is None:
        return None, 0.0
    started = time.monotonic()
    last = before
    changed = False
    while time.monotonic() - started < SETTLE_MAX_SECONDS:
        time.sleep(SETTLE_INTERVAL_SECONDS)
        now = screen_digest(be, region)
        if now is None:
            return None, round(time.monotonic() - started, 2)
        if now != before:
            changed = True
        if changed and now == last:
            break
        last = now
    return changed, round(time.monotonic() - started, 2)


def save_shot(be, args, region: list[int] | None, name: str | None) -> str | None:
    """Save the capture and return its path (WebP, long side 1200px — same as app and web)."""
    png = be.grab(region)
    if not png:
        return None
    raw, explicit = shot_target(project_root(args), name, ".png")
    Path(raw).write_bytes(png)
    return str(finish_shot(Path(raw), explicit, args))


def secret_text(args) -> tuple[str | None, bool, dict | None]:
    """(input value, is secret, failure result). --text-env and --cred are secret, --text is plain."""
    if getattr(args, "text_env", None):
        value = os.environ.get(args.text_env)
        if value is None:
            return None, True, {"ok": False, "code": "env_not_set",
                                "error": f"Environment variable {args.text_env} is empty",
                                "hint": f'Prefix the same command with {args.text_env}="..."'}
        return value, True, None
    if getattr(args, "cred", None):
        value, err = cred_field(args.cred, getattr(args, "cred_field", None))
        return value, True, err
    return getattr(args, "text", None), False, None


def masked(text: str, secret: str | None) -> str:
    return text.replace(secret, "***") if secret and len(secret) >= 4 else text
