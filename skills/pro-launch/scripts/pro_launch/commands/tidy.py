"""`tidy` — by default merges scattered memories (old behavior). `tidy --buckets` reports accumulated state · cleans only with --apply (#932).

4 things --buckets looks at: buckets (size, last use, fake/temp, orphan profiles), Maestro test output (~/.maestro/tests),
projectops tmp, stale memories. Default is report only (dry). With --apply only the following is removed.
  · fake/temp buckets unused for more than --days days (ones holding data files are kept)
  · profiles of buckets left with only a profile and no state file (unused for more than --days days)
  · Maestro test folders · projectops tmp entries older than --days days
  · apply the stale-memory table (mark superseded · delete test pollution)
Profiles with a live browser process or that look in use are never removed.
Buckets of real repos (owner__repo key · known local repo) keep both profile and data; only size and age are reported.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

from common.state import KINDS, MACHINE_BUCKET, SCRATCH_BUCKET, base_dir

import knowledge
import knowledge_stale
import maestro_runs

from pro_launch.registry import Command
from pro_launch.runtime import browser_profiles, device_ledger
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import pid_alive, process_command_lines
from pro_launch.runtime.recent_roots import load_recent_roots

SECONDS_PER_DAY = 86400
DEFAULT_IDLE_DAYS = 7
# <owner>__<repo> — a normal repo key derived from the git remote
REPO_KEY_PATTERN = re.compile(r"^[^/_][^/]*__[^/]+$")
# Folders not treated as buckets (machine-wide · session relay · virtualenv) + _scratch, looked into one level deeper
RESERVED_NAMES = (MACHINE_BUCKET, SCRATCH_BUCKET, "maestro-sessions", ".venv")
PROFILE_NAME = ".browser-profile"
# With this file present, it is not a disposable temp folder (data left by a person or agent)
DATA_FILES = ("access.json", "learned.json", "devices.json", "journal.json", "app-map.json")
BROWSER_STATE_FILE = "browser.json"


def _tree_size(path: Path) -> int:
    """Total bytes of a folder (does not follow links). Unreadable entries are skipped."""
    total = 0
    stack = [str(path)]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _last_used(path: Path) -> float:
    """Most recent mtime of the folder and its direct children (does not look inside profiles)."""
    latest = 0.0
    try:
        latest = path.stat().st_mtime
        for child in path.iterdir():
            latest = max(latest, child.lstat().st_mtime)
    except OSError:
        pass
    return latest


def _megabytes(size_bytes: int) -> float:
    return round(size_bytes / 1_000_000, 1)


def _bucket_has_data(path: Path) -> bool:
    """Is there data a person left (access method · memory · location records)?"""
    if any((path / name).exists() for name in DATA_FILES):
        return True
    return bool(knowledge.load(path / knowledge.FILE))


def _live_browser_pid(path: Path) -> int | None:
    """The pid from browser.json if it is alive."""
    try:
        pid = int(json.loads((path / BROWSER_STATE_FILE).read_text(encoding="utf-8")).get("pid") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return pid if pid and pid_alive(pid) else None


def _is_profile_in_use(profile: Path, command_lines: str | None) -> bool:
    """Is a process using this profile? If the process list cannot be read, treat as in use."""
    return True if not command_lines else str(profile) in command_lines


def _known_folder_names() -> set[str]:
    """Folder names of recent roots (repos) — matched against bucket names of local repos without a remote."""
    return {Path(row["path"]).name for row in load_recent_roots()}


def _classify(parent_name: str, name: str, known_names: set[str]) -> str:
    """real (remote key · known local repo) | scratch (under _scratch) | fake (any other folder name)."""
    if parent_name == SCRATCH_BUCKET:
        return "scratch"
    if REPO_KEY_PATTERN.match(name) or name in known_names:
        return "real"
    return "fake"


def _bucket_rows(command_lines: str | None, now: float) -> list[dict]:
    known = _known_folder_names()
    rows = []
    for kind in KINDS:
        kind_dir = base_dir() / kind
        if not kind_dir.is_dir():
            continue
        candidates = []
        for child in sorted(kind_dir.iterdir()):
            if not child.is_dir() or (child.name in RESERVED_NAMES and child.name != SCRATCH_BUCKET):
                continue
            if child.name == SCRATCH_BUCKET:
                candidates += [(grand, SCRATCH_BUCKET) for grand in sorted(child.iterdir()) if grand.is_dir()]
            else:
                candidates.append((child, kind))
        marked_bucket_names = _buckets_with_profile_marks()
        for path, parent_name in candidates:
            profile = path / PROFILE_NAME
            has_profile = profile.is_dir()
            live_pid = _live_browser_pid(path)
            last_used = _last_used(path)
            rows.append({
                "kind": kind, "name": path.name, "path": str(path),
                "classification": _classify(parent_name, path.name, known),
                "size_mb": _megabytes(_tree_size(path)),
                "profile_mb": _megabytes(_tree_size(profile)) if has_profile else 0,
                "last_used": time.strftime("%Y-%m-%d %H:%M", time.localtime(last_used)) if last_used else None,
                "idle_days": round((now - last_used) / SECONDS_PER_DAY, 1) if last_used else None,
                "has_data": _bucket_has_data(path),
                # Profile of a bucket left with only a profile and no state (data)
                "is_orphan_profile": has_profile and not _bucket_has_data(path),
                "is_browser_alive": live_pid is not None or (has_profile and _is_profile_in_use(profile, command_lines)),
                # Profile with recorded effortful state such as a login (#956)
                "has_profile_marks": has_profile and path.name in marked_bucket_names,
            })
    return rows


def _buckets_with_profile_marks() -> set[str]:
    """Bucket names with a mark on their repo profile (ledger key browser-profile:repo:<bucket>)."""
    prefix = f"{browser_profiles.MARK_KEY_PREFIX}repo:"
    return {key[len(prefix):] for key, entry in device_ledger.read_ledger()["devices"].items()
            if key.startswith(prefix) and entry.get("marks")}


def _decide_bucket_action(row: dict, idle_days: float) -> str:
    """Handling for one bucket: delete_bucket | delete_profile | keep (reason in skipped_reason)."""
    if row["is_browser_alive"]:
        return "keep:browser_alive"
    # Deleting a profile with a recorded login means logging in and 2FA again
    if row.get("has_profile_marks"):
        return "keep:profile_has_marks"
    # For real repos, login profiles are user assets too — report only
    if row["classification"] == "real" and row["is_orphan_profile"]:
        return "keep:real_repo_profile"
    is_idle = row["idle_days"] is not None and row["idle_days"] > idle_days
    if not is_idle:
        return "keep:recently_used"
    if row["classification"] != "real" and not row["has_data"]:
        return "delete_bucket"
    if row["is_orphan_profile"] and row["classification"] != "real":
        return "delete_profile"
    return "keep:not_junk"


def _maestro_rows(idle_days: float, now: float) -> dict:
    folder = maestro_runs.maestro_tests_folder()
    old, total_bytes, count = [], 0, 0
    if folder.is_dir():
        for child in folder.iterdir():
            if not child.is_dir():
                continue
            count += 1
            total_bytes += _tree_size(child)
            if now - child.stat().st_mtime > idle_days * SECONDS_PER_DAY:
                old.append(child)
    return {"path": str(folder), "count": count, "size_mb": _megabytes(total_bytes),
            "old_count": len(old), "_old": old}


def _tmp_rows(idle_days: float, now: float) -> dict:
    folder = base_dir() / "tmp"
    old = []
    if folder.is_dir():
        old = [c for c in folder.iterdir() if now - c.lstat().st_mtime > idle_days * SECONDS_PER_DAY]
    return {"path": str(folder), "size_mb": _megabytes(_tree_size(folder)) if folder.is_dir() else 0,
            "old_count": len(old), "_old": old}


def _remove(path: Path) -> bool:
    try:
        shutil.rmtree(path) if path.is_dir() and not path.is_symlink() else path.unlink()
        return True
    except OSError:
        return False


def _knowledge_stale_rows() -> list[dict]:
    rows = []
    for scope, store in (("machine", knowledge.store_path("machine", Path("."))),):
        rows += [{**match, "scope": scope} for match in knowledge_stale.stale_matches(store)]
    return rows


def _apply(buckets: list[dict], maestro: dict, tmp: dict, idle_days: float) -> tuple[list[str], list[dict]]:
    removed, skipped = [], []
    for row in buckets:
        action = row["action"]
        path = Path(row["path"])
        if action == "delete_bucket":
            ok = _remove(path)
        elif action == "delete_profile":
            ok = _remove(path / PROFILE_NAME)
            (path / BROWSER_STATE_FILE).unlink(missing_ok=True)
        else:
            if row["classification"] != "real":
                skipped.append({"path": row["path"], "reason": action.split(":", 1)[-1]})
            continue
        (removed if ok else skipped).append(row["path"] if ok else {"path": row["path"], "reason": "remove_failed"})
    for group in (maestro, tmp):
        removed += [str(p) for p in group["_old"] if _remove(p)]
    return removed, skipped


def cmd_tidy(args) -> int:
    if not args.buckets:
        if args.apply:
            return out({"ok": False, "code": "bad_args", "error": "--apply is used together with --buckets",
                        "next": "tidy --buckets [--apply] [--days N]"})
        merged = knowledge.tidy()
        return out({"ok": True, "code": "ok", **merged,
                    "summary": f"Moved {merged['moved_to_machine']} entries to the machine scope ({merged['merged']} merged)",
                    "next": "recall --scope machine  # see the result"})
    now = time.time()
    command_lines = process_command_lines()
    buckets = _bucket_rows(command_lines, now)
    for row in buckets:
        row["action"] = _decide_bucket_action(row, args.days)
    maestro, tmp = _maestro_rows(args.days, now), _tmp_rows(args.days, now)
    stale_knowledge = _knowledge_stale_rows()
    removed: list[str] = []
    skipped: list[dict] = []
    if args.apply:
        removed, skipped = _apply(buckets, maestro, tmp, args.days)
        applied_knowledge = [knowledge_stale.apply_stale_table(knowledge.store_path("machine", Path(".")))]
        stale_knowledge = [m for rows in applied_knowledge for m in rows]
    deletable = [r for r in buckets if r["action"].startswith("delete")]
    total_mb = _megabytes(int(sum(r["size_mb"] for r in buckets) * 1_000_000))
    summary = (f"Cleaned up {len(removed)} item(s)" if args.apply else
               f"{len(buckets)} bucket(s) {total_mb}MB · {len(deletable)} cleanup candidate(s) · Maestro {maestro['count']} "
               f"{maestro['size_mb']}MB (report only — use --apply to delete)")
    return out({"ok": True, "code": "ok", "mode": "apply" if args.apply else "dry", "idle_days": args.days,
                "buckets": sorted(buckets, key=lambda r: -r["size_mb"]), "total_mb": total_mb,
                "maestro_tests": {k: v for k, v in maestro.items() if k != "_old"},
                "projectops_tmp": {k: v for k, v in tmp.items() if k != "_old"},
                "stale_knowledge": stale_knowledge, "removed": removed, "skipped": skipped,
                "summary": summary,
                "next": ("tidy --buckets --apply  # deletes only cleanup candidates (action: delete_*) and old Maestro output"
                         if not args.apply and (deletable or maestro["old_count"]) else None)})


def configure_tidy(p) -> None:
    p.add_argument("--buckets", action="store_true",
                   help="Instead of merging memory, report accumulated state (buckets · profiles · Maestro output · tmp · stale memory)")
    p.add_argument("--apply", action="store_true", help="With --buckets: clean up instead of only reporting")
    p.add_argument("--days", type=float, default=DEFAULT_IDLE_DAYS,
                   help=f"Only clean up items unused for longer than this many days (default {DEFAULT_IDLE_DAYS})")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="tidy", help="Tidy scattered memory (--buckets: report accumulated state · cleans up only with --apply)",
            run=cmd_tidy, configure=configure_tidy),
]
