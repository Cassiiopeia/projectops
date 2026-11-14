"""Record locations: project key, scenario and note folders under home, scenario lookup and precondition expansion"""
from __future__ import annotations

from pathlib import Path

from common.state import repo_key, state_dir

# Record file names · note summary sizes
_NOTE_FILE = "learned.json"
_SEEN_FILE = "memory_seen.json"     # days memory was surfaced in responses (once per day and area)
_MACHINE = "_machine"               # ~/.projectops/agent-test/_machine/ — machine scope

_SHOW_MAX = 5                       # note show summary: this many constraints and pitfalls each
_SHOW_CHARS = 120                   # characters per entry in the summary
_SURFACE_CHARS = 200                # characters per entry surfaced in responses (principle: 200 chars)
_NOTE_MIN_WORDS = 3                 # short sentences with fewer distinct words are never auto-merged
_MACHINE_SCOPES = ("flutter", "platform")


def _repo_key(root: Path) -> str:
    """Key identifying the project (decided solely by common/state.py)."""
    return repo_key(root)


def _home_dir(root: Path) -> Path:
    """Where accumulated data (learned.json · scenarios · flows) lives. Outside the project (home), so it survives new worktrees.

    Device, browser and access info lives in pro-launch's location (~/.projectops/launch/) (#629).
    """
    return state_dir("agent-test", root)


def _scenario_dir(root: Path, create: bool = False) -> Path:
    """Where scenarios and knowledge go.

    Kept in home, with projects told apart by git remote. A folder inside the project excluded by .gitignore
    **is not copied into new worktrees**, so knowledge vanishes in the worktree-per-issue flow (#586).
    """
    home = _home_dir(root)
    if create and not home.is_dir():
        home.mkdir(parents=True, exist_ok=True)
    return home

def _scenario_files(d: Path) -> list[Path]:
    """List scenario files. Looks at flows/ subfolders and _shared/ together.

    app-map and learned are not scenarios and are excluded.
    """
    if not d.is_dir():
        return []
    # app-map is a bootstrap-era output, memory_seen records days memory was surfaced (#837)
    skip = {"app-map.json", _NOTE_FILE, _SEEN_FILE}
    out = [f for f in d.rglob("*.json")
           if f.name not in skip and not f.name.startswith("learned.broken-")]
    return sorted(out)


def _resolve_scenario(d: Path, name: str) -> Path | None:
    """Find a file by name. Accepts a path like `flows/auth/x` or just `x`."""
    direct = d / f"{name}.json"
    # Files outside the folder (../x) are not scenarios (#707)
    if direct.exists() and d.resolve() in direct.resolve().parents:
        return direct
    matches = [f for f in _scenario_files(d) if f.stem == name]
    return matches[0] if len(matches) == 1 else None


def _expand(d: Path, path: Path, seen: list[str] | None = None) -> tuple[dict, list[str]]:
    """Expand preconditions into the full step list.

    Keeps flows that precede almost every scenario, like login, from being written each time.
    Circular references are cut here — reported as a problem instead of dying in infinite recursion.
    """
    import json
    seen = seen or []
    key = str(path)
    if key in seen:
        return {}, [f"Precondition cycle: {' → '.join(seen + [key])}"]
    data = json.loads(path.read_text(encoding="utf-8"))
    pre = data.get("precondition")
    if not pre:
        return data, []

    target = _resolve_scenario(d, pre)
    if target is None:
        return data, [f"Precondition '{pre}' not found"]
    base, problems = _expand(d, target, seen + [key])
    merged = dict(data)
    merged["steps"] = list(base.get("steps", [])) + list(data.get("steps", []))
    merged["_precondition_steps"] = len(base.get("steps", []))
    if base.get("reset") and not data.get("reset"):
        merged["reset"] = base["reset"]
    return merged, problems
