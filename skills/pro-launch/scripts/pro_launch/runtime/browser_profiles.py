"""Picking the browser profile: repo profile · named profiles shared on this computer (#956).

The repo profile is one per repo bucket as before ({state_home}/.browser-profile). To share a sign-in across repos
use a shared profile ({base}/launch/_machine/browser-profiles/<name>/). The chosen profile is remembered per repo (web-profile.json).
A profile folder can be opened by only one browser — shared profiles too have several sessions share one browser over CDP (tab ownership #878).
Prepared states like sign-in are kept as marks in the same ledger as devices (keys: browser-profile:<name> · browser-profile:repo:<bucket>).
Profile pick is also kept per session in the same file, so sessions in one repo do not swap browsers (#1154).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from common.state import MACHINE_BUCKET, base_dir

from pro_launch.runtime import device_ledger
from pro_launch.runtime.browser import PROFILE_FOLDER_NAME, WEB_STATE_FILE_NAME, state_path
from pro_launch.runtime.context import state_home
from pro_launch.runtime.session_identity import session_identity

# Shared profile set explicitly (wins over the repo memory)
PROFILE_ENV_VAR = "LAUNCH_WEB_PROFILE"
# Repo memory file · name that goes back to the repo profile
PROFILE_CHOICE_FILE = "web-profile.json"
REPO_PROFILE_NAME = "repo"
# web-profile.json: per-session picks {session: {name, at}} next to the repo default "name" (#1154)
SESSION_CHOICES_KEY = "sessions"
# Sessions remembered per repo (oldest dropped first)
MAX_SESSION_CHOICES = 32
_PROFILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
MARK_KEY_PREFIX = "browser-profile:"


def shared_profiles_root() -> Path:
    return base_dir() / "launch" / MACHINE_BUCKET / "browser-profiles"


def is_valid_profile_name(name: str) -> bool:
    return bool(_PROFILE_NAME_PATTERN.match(name or "")) and name != REPO_PROFILE_NAME


def chosen_profile(root: Path) -> str | None:
    """Shared profile this session uses (env var > this session's pick > repo memory). None means the repo profile."""
    from_env = (os.environ.get(PROFILE_ENV_VAR) or "").strip()
    if from_env:
        return None if from_env == REPO_PROFILE_NAME else from_env
    choice = _read_choice(root)
    # Per-session pick first: another session's --profile must not move this session to its browser (#1154)
    session_entry = (choice.get(SESSION_CHOICES_KEY) or {}).get(session_identity())
    name = session_entry.get("name") if isinstance(session_entry, dict) else choice.get("name")
    if name == REPO_PROFILE_NAME:
        return None
    return name if isinstance(name, str) and is_valid_profile_name(name) else None


def choose_profile(root: Path, name: str | None) -> None:
    """Remember the profile for this session and as the repo default for new sessions (None · repo = repo profile)."""
    choice = _read_choice(root)
    if not name or name == REPO_PROFILE_NAME:
        choice.pop("name", None)
    else:
        choice["name"] = name
    _write_choice(root, _with_session_pin(choice, name or REPO_PROFILE_NAME))


def pin_session_profile(root: Path) -> None:
    """Pin this session to the profile it resolves to now, so a later repo-default change by another session does not move it."""
    if (os.environ.get(PROFILE_ENV_VAR) or "").strip():
        return
    choice = _read_choice(root)
    _write_choice(root, _with_session_pin(choice, chosen_profile(root) or REPO_PROFILE_NAME))


def _with_session_pin(choice: dict, name: str) -> dict:
    """choice > same dict with this session's pick set, keeping only the most recent MAX_SESSION_CHOICES sessions."""
    sessions = {key: value for key, value in (choice.get(SESSION_CHOICES_KEY) or {}).items() if isinstance(value, dict)}
    sessions.pop(session_identity(), None)
    sessions[session_identity()] = {"name": name, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    # Dicts keep insertion order: the re-inserted entry is newest, the first ones are oldest
    choice[SESSION_CHOICES_KEY] = dict(list(sessions.items())[-MAX_SESSION_CHOICES:])
    return choice


def _read_choice(root: Path) -> dict:
    try:
        data = json.loads((state_home(root) / PROFILE_CHOICE_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_choice(root: Path, choice: dict) -> None:
    """Atomic write (temp file > replace): sessions write this file concurrently."""
    choice_file = state_home(root) / PROFILE_CHOICE_FILE
    choice_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = choice_file.with_name(f"{choice_file.name}.{os.getpid()}.tmp")
    temporary_file.write_text(json.dumps(choice, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary_file, choice_file)


def profile_home(root: Path) -> Path:
    """Where the profile folder · browser state · stderr log live."""
    name = chosen_profile(root)
    if not name:
        return state_home(root)
    folder = shared_profiles_root() / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def web_state_path(root: Path) -> Path:
    """Browser state file web commands read and write — the profile's spot for shared profiles."""
    return (profile_home(root) / WEB_STATE_FILE_NAME) if chosen_profile(root) else state_path(root)


def profile_mark_key(root: Path, name: str | None = None) -> str:
    """Ledger key: browser-profile:<name> for shared, browser-profile:repo:<bucket name> for the repo profile."""
    chosen = name if name is not None else chosen_profile(root)
    if chosen and chosen != REPO_PROFILE_NAME:
        return f"{MARK_KEY_PREFIX}{chosen}"
    return f"{MARK_KEY_PREFIX}repo:{state_home(root).name}"


def shared_profile_names() -> list[str]:
    """Shared profile names: those with a folder + those only recorded in the ledger (never launched yet)."""
    root = shared_profiles_root()
    folders = {p.name for p in root.iterdir() if p.is_dir()} if root.is_dir() else set()
    recorded = {key[len(MARK_KEY_PREFIX):] for key in device_ledger.read_ledger()["devices"]
                if key.startswith(MARK_KEY_PREFIX) and not key.startswith(f"{MARK_KEY_PREFIX}repo:")}
    return sorted(folders | recorded)


def profile_with_marks(root: Path, needs: list[str]) -> str | None:
    """Profile that has every --need: repo profile > shared profiles (by name) > None. 'repo' for the repo profile."""
    devices = device_ledger.read_ledger()["devices"]

    def has_all(key: str) -> bool:
        labels = {f"{m.get('kind')}:{m.get('name')}" for m in (devices.get(key) or {}).get("marks") or []}
        return all(need in labels for need in needs)

    if has_all(profile_mark_key(root, REPO_PROFILE_NAME)):
        return REPO_PROFILE_NAME
    return next((name for name in shared_profile_names() if has_all(profile_mark_key(root, name))), None)


def all_web_state_files() -> list[Path]:
    """Every browser state file on this computer (repo buckets · shared profiles) — for session-end cleanup."""
    launch_root = base_dir() / "launch"
    if not launch_root.is_dir():
        return []
    return sorted(set(launch_root.glob(f"*/{WEB_STATE_FILE_NAME}")) | set(launch_root.glob(f"*/*/{WEB_STATE_FILE_NAME}"))
                  | set(shared_profiles_root().glob(f"*/{WEB_STATE_FILE_NAME}")))


def other_session_tabs(state: dict, session: str) -> list[str]:
    """Tab records in the state that belong to other sessions (key: tab name@session)."""
    return [key for key in (state.get("tab_marks") or {}) if not key.endswith(f"@{session}")]


