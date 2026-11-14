"""Where skills keep their state: outside the project, under home (shared by pro-launch · pro-agent-test, #629).

    ~/.projectops/launch/<owner__repo>/      devices.json · browser.json · access.json ·
                                             .browser-profile/ · shots/
    ~/.projectops/launch/.venv               Playwright · Pillow
    ~/.projectops/agent-test/<owner__repo>/  learned.json · scenarios · flows/

Running and capturing ("how to attach") belongs to pro-launch; scenarios and knowledge belong to agent-test.
Launch files left in the old agent-test folder are moved on the first call.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from common.proc import pid_alive

KINDS = ("launch", "agent-test")

# launch's share. The rest (learned.json · scenarios · flows) stays with agent-test.
LAUNCH_OWNED = ("devices.json", "browser.json", "access.json", ".browser-profile", "shots")
# Must not move while the browser is up: the profile is in use and the state file points to that path
_BROWSER_FILES = ("browser.json", ".browser-profile")


# Machine-wide bucket used when the repo is unknown (called from a skill or plugin cache folder) (#836)
MACHINE_BUCKET = "_machine"

# Where skills and plugins live. Called from here without a git remote, it is not a user project.
_SKILL_PATH_MARKERS = ("/skills/pro-", "/plugins/cache/")

# Bucket for folders with no git and no project marker (scratchpad · /tmp · jobs/tmp): <kind>/_scratch/<folder name>-<8-char path hash> (#932)
SCRATCH_BUCKET = "_scratch"
# If this file is at the root, treat it as a user project even without git (folder-name key kept)
PROJECT_MARKER_FILES = ("pubspec.yaml", "package.json", "pyproject.toml", "build.gradle", "build.gradle.kts",
                        "settings.gradle", "settings.gradle.kts", "pom.xml", "Podfile", "Cargo.toml", "go.mod",
                        "version.yml")


def base_dir() -> Path:
    """State root. PROJECTOPS_HOME if set; the escape hatch that keeps tests off the real home (#836).

    Changing HOME hangs Chrome on macOS (measured), so browser tests change only this variable.
    """
    env = os.environ.get("PROJECTOPS_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".projectops"


def _origin_url(root: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def in_skill_path(root: Path) -> bool:
    """Whether root is inside a skill or plugin cache folder (path check only; git is not called)."""
    s = Path(root).resolve().as_posix() + "/"
    return any(m in s for m in _SKILL_PATH_MARKERS)


def repo_unknown(root: Path) -> bool:
    """The project is unknown: called from a skill or plugin cache folder with no git remote.

    Using the folder name (`scripts`, etc.) as the repo key would create fake buckets and scatter state and memory (#833·#836).
    A checkout with a remote, like a dev checkout, counts as a normal repo.
    """
    return in_skill_path(root) and not _origin_url(root)


def is_inside_git_work_tree(root: Path) -> bool:
    """Whether root or a parent has .git (folder or worktree file); git is not called (runs on every command)."""
    resolved = Path(root).resolve()
    return any((folder / ".git").exists() for folder in (resolved, *resolved.parents))


def is_scratch_root(root: Path) -> bool:
    """Whether this is a temp folder with no git and no project marker. Folder names (tmp · root · site) as bucket keys would mix with others' state (#932)."""
    resolved = Path(root).resolve()
    if is_inside_git_work_tree(resolved) or in_skill_path(resolved):
        return False
    return not any((resolved / marker).exists() for marker in PROJECT_MARKER_FILES)


def scratch_key(root: Path) -> str:
    """Temp folder bucket name: <folder name>-<8-char sha1 of the absolute path>, distinct from other folders with the same name."""
    resolved = Path(root).resolve()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", resolved.name).strip("-") or "local"
    return f"{slug}-{hashlib.sha1(str(resolved).encode('utf-8')).hexdigest()[:8]}"


def repo_key(root: Path) -> str:
    """Key that identifies the project. Uses owner/repo from the git remote.

    **Never key by path.** Each worktree has a different path, so one project would split
    into many, and accumulated knowledge would be divided by the number of worktrees.
    Repositories without a remote (local only) fall back to the folder name; non-ASCII names get a path hash.
    """
    url = _origin_url(root)
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url) if url else None
    if m:
        return f"{m.group(1)}__{m.group(2)}"
    # Repository without a remote: if the folder name already uses only safe characters, keep the old key (preserve existing state).
    # Non-ASCII names like Hangul lose their characters when replaced and collapse to `unknown`/`repo`, so different
    # repositories would share state; only then append the absolute path hash to tell them apart (#702).
    name = Path(root).name
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    if slug and slug == name:
        return slug
    digest = hashlib.sha1(str(Path(root).resolve()).encode("utf-8")).hexdigest()[:8]
    return f"{slug or 'local'}-{digest}"


def state_dir(kind: str, root: Path) -> Path:
    """State folder per kind. Not created here; callers create it when needed.

    If the repo is unknown, use the machine-wide slot (`_machine`) instead of a fake bucket (#836).
    Temp folders without git or markers use a path-hash bucket (`_scratch/<name>-<hash>`) (#932).
    """
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    if repo_unknown(root):
        return base_dir() / kind / MACHINE_BUCKET
    if is_scratch_root(root):
        return base_dir() / kind / SCRATCH_BUCKET / scratch_key(root)
    return base_dir() / kind / repo_key(root)


def migrate_launch(root: Path) -> dict:
    """Move launch's share from the old agent-test folder to the launch folder.

    - Leave it alone if already in the new folder (idempotent: nothing happens from the second run on)
    - If the browser is up, defer browser-related items (moving an in-use profile breaks it)
    - If a move fails, only warn so the old path keeps being read; the feature must not stop
    """
    old = state_dir("agent-test", root)
    new = state_dir("launch", root)
    moved: list[str] = []
    warnings: list[str] = []
    if not old.is_dir():
        return {"moved": moved, "warnings": warnings}

    browser_busy = False
    bj = old / "browser.json"
    if bj.is_file():
        try:
            browser_busy = pid_alive(json.loads(bj.read_text(encoding="utf-8")).get("pid"))
        except (OSError, json.JSONDecodeError, AttributeError):
            browser_busy = False

    for name in LAUNCH_OWNED:
        src, dst = old / name, new / name
        if not src.exists() or dst.exists():
            continue
        if browser_busy and name in _BROWSER_FILES:
            warnings.append(f"{name}: not moved because the browser is open; it moves after web close")
            continue
        try:
            new.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved.append(name)
        except OSError as e:
            warnings.append(f"{name}: could not move ({e}); still using the old location")

    # If the state file still holds the old profile path, point it to the new location
    nbj = new / "browser.json"
    if "browser.json" in moved and nbj.is_file():
        try:
            data = json.loads(nbj.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("profile"):
                data["profile"] = str(new / ".browser-profile")
                nbj.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    return {"moved": moved, "warnings": warnings}


def launch_file(root: Path, name: str) -> Path:
    """Actual location of a launch-share file. If missing in the new location and present only in the old one, use the old one.

    A safety net so features keep working even when the migration failed.
    """
    new = state_dir("launch", root) / name
    if new.exists():
        return new
    old = state_dir("agent-test", root) / name
    return old if old.exists() else new


# ── Dedicated virtual environment ───────────────────────────────────────
#
# Not installed into system Python: macOS Homebrew Python blocks pip via PEP 668.
# The old location (agent-test/.venv) is not moved; no reason to re-download ~100MB.

def venv_dir() -> Path:
    new = base_dir() / "launch" / ".venv"
    candidates = [new, base_dir() / "agent-test" / ".venv"]
    # Even when only state was moved via PROJECTOPS_HOME, reuse an already installed venv (an install, not state).
    # Read only: a new one is always created under base_dir().
    real = Path.home() / ".projectops"
    if real != base_dir():
        candidates += [real / "launch" / ".venv", real / "agent-test" / ".venv"]
    for d in candidates:
        if _venv_exe(d):
            return d
    return new   # where to create it if not there yet


def _venv_exe(d: Path) -> Path | None:
    exe = d / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python")
    return exe if exe.is_file() else None


def venv_python() -> Path | None:
    return _venv_exe(venv_dir())


def venv_site_packages() -> Path | None:
    d = venv_dir()
    for pat in ("lib/python*/site-packages", "Lib/site-packages"):
        for sp in d.glob(pat):
            if sp.is_dir():
                return sp
    return None
