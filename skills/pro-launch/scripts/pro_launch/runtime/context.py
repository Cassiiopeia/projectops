"""State of one run — project root resolution and markers passed between commands."""
from __future__ import annotations

import os
from pathlib import Path

from common.state import base_dir, in_skill_path, is_scratch_root, migrate_launch, repo_unknown, state_dir

from pro_launch.runtime.recent_roots import is_git_work_tree, last_used_root, remember_root


# Whether this process already migrated. Checked only once.
MIGRATION: dict = {}


def state_home(root: Path) -> Path:
    """launch state folder. On first call, moves the launch share of the old agent-test folder."""
    key = str(root)
    if key not in MIGRATION:
        MIGRATION[key] = migrate_launch(root)
    return state_dir("launch", root)


# ── When the repo cannot be known (#836) ──────────────────────────────────────────
#
# Called from a skill·plugin cache folder with no git remote means the project is unknown. Then state
# goes to this computer's shared spot (_machine) (state.state_dir decides) and the response asks for --root.
ROOT_CTX: dict = {}


# ── Track record of recorded connection methods (#836) ──────────────────────────────────────
#
# When logs·db·http run from an access record, the tool records the result itself (memory principle 2).
# Environment-caused failures like missing installs or env vars are not the method's fault, so they are not counted.
ACCESS_CTX: dict = {}


# ── Attaching memory to responses (#833) ──────────────────────────────────────────
#
# Leaving reads to the agent's recall call meant memories were never read again (observed: all 14 entries ok=1).
# So memory is attached directly to responses of area (ios·android·web·server) commands — shown regardless of harness.
# A command that sets an area writes it to MEMORY_CTX, and out() reads it at the end.
MEMORY_CTX: dict = {}


# ── Where this command is aimed (projectops#1023) ──────────────────────────────
#
# url · host · app · window · area · root. out() attaches harnesses (harness_store) matching this URL·host·app·window to the response.
# Unlike area memory, also used for commands without a set area, like ssh --host given without saving.
# app: package name·bundle ID (app commands, area=app) · window: window title·program name list (desktop commands) — projectops#1024
TARGET_CTX: dict = {}


# ── Output shape (#898) ──────────────────────────────────────────────────────
#
# Reading results cut with head·cut·python discarded next·memory·known_fix (observed 636+275 times).
# cli.main writes global --brief · --fields here, and out() reads them last to trim.
# is_brief: core keys only / field_names: top-level keys to keep (None keeps all)
OUTPUT_CTX: dict = {}


# ── Input markers (#886) ──────────────────────────────────────────────────────
#
# empty_values: options passed as empty strings. Attached to failed responses — the cause is often an unset $VAR
INPUT_CTX: dict = {}


def project_root(args) -> Path:
    """Target project root: --root > $PROJECT_ROOT > working folder (if git) > recently used root > working folder (#885).

    Agent shells reset the working folder every call, so calls from outside the repo hit git_not_found·browser_not_open.
    When the agent `cd`s into the scripts folder and calls with `--root .`, the plugin cache was taken as the repo and memories
    piled up in the wrong place (~/.projectops/launch/scripts/) (observed in #833) — $PROJECT_ROOT is used then too.
    """
    raw = getattr(args, "root", ".") or "."
    cache_key = (raw, os.getcwd(), os.environ.get("PROJECT_ROOT"), str(base_dir()))
    if cache_key not in _RESOLVED_ROOTS:
        _RESOLVED_ROOTS[cache_key] = _resolve_root(raw)
    root, marks = _RESOLVED_ROOTS[cache_key]
    ROOT_CTX.update(marks, resolved=str(root))
    return root


# (--root value, working folder, $PROJECT_ROOT) > (root, ROOT_CTX marker). git is checked once even if one command calls project_root many times
_RESOLVED_ROOTS: dict = {}


def _resolve_root(raw: str) -> tuple[Path, dict]:
    env_root = os.environ.get("PROJECT_ROOT")
    candidate = Path(raw).expanduser().resolve()
    if raw != ".":
        if repo_unknown(candidate):
            if env_root:
                return _remembered(Path(env_root).expanduser().resolve()), {}
            # state_dir redirects state to _machine. Just mark it so the response asks for --root
            return candidate, {"unknown": True, "path": str(candidate)}
        if is_scratch_root(candidate):
            # Explicit root without git·markers (scratchpad etc.) — path-hash bucket, not kept as a recent root (#932)
            return candidate, {"scratch": True, "path": str(candidate)}
        # Explicit repo root: a failure here is not "called from the wrong folder" (#1154)
        return _remembered(candidate), {"explicit": True}
    if env_root:
        return _remembered(Path(env_root).expanduser().resolve()), {}
    if is_git_work_tree(candidate) and not repo_unknown(candidate):
        return _remembered(candidate), {}
    last = last_used_root()
    if last is not None:
        return last, {"source": "last_used", "path": str(last), "cwd": str(candidate)}
    if repo_unknown(candidate):
        return candidate, {"unknown": True, "path": str(candidate)}
    # Folder that is not a git repo — use it as before, but on failure attach candidates and the command to rerun
    return candidate, {"not_repo": True, "path": str(candidate), "scratch": is_scratch_root(candidate)}


def _remembered(root: Path) -> Path:
    # If a temp folder became the recent root, calls from outside the repo would use it (#932)
    if not is_scratch_root(root):
        remember_root(root)
    return root


# scripts/ folder — this file is under scripts/pro_launch/runtime/
SCRIPTS_DIR = Path(__file__).resolve().parents[2]


def is_skill_dir(r: Path) -> bool:
    """Is r inside a skill·plugin folder (including this skill itself) — may not be a user project."""
    return r in (SCRIPTS_DIR, SCRIPTS_DIR.parent) or in_skill_path(r)
