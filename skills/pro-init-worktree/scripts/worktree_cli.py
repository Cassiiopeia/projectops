#!/usr/bin/env python3
"""worktree_cli — remembers pro-init-worktree's local file copy set (#839).

Re-judging gitignored local file candidates from scratch for every worktree costs tokens.
The set to copy is nearly the same per repo, so **remember last time's set and judge only changed candidates**.

    recall --root <repo>                       last set + difference from current candidates
    record --root <repo> --copied a,b --skipped c   record the set right after copying (paths only)
    create --root <repo> --branch B [--base origin/develop]   create a worktree
    copy   --root <repo> --to <worktree> [--files a,b]        copy the remembered set
    remove --root <repo> --path|--branch B [--force]          safe removal

Stored at: ~/.projectops/worktree/<owner__repo>.json (memory principle §5 — local home, never committed to the repo)
Keyed by `repo_key`, so the original and any worktree see the same memory.

**File contents are never stored.** Targets include secret files like `.env` and keystores,
so only relative paths are kept. Value-like input (absolute paths, `..`, newlines, `=`) is rejected.

Output: every subcommand prints stdout JSON (ok/code/summary/next).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

# Bootstrap — scripts/common import (cwd-independent)
_HERE = Path(__file__).resolve()
_SCRIPTS_ROOT = _HERE.parents[3] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402
from common.emit import emit  # noqa: E402
from common.state import base_dir, repo_key  # noqa: E402

sys.path.insert(0, str(_HERE.parent))
import worktree_ops  # noqa: E402

SCHEMA = 1
MAX_BYTES = 1024 * 1024  # files over 1MB are likely not config files (local-files.md 4-3)

# Regenerable caches, build outputs, IDE state — excluded from candidates (same list as local-files.md 4-2 + Python/web caches)
EXCLUDE_MARKERS = (
    "build/", "target/", ".gradle", "node_modules", "Pods/", ".dart_tool",
    "Generated", "generate", ".last_build_id", ".framework", ".flx", ".zip",
    "DerivedData", "XCBuildData", ".class", ".pyc", ".log", ".symbols", ".map.json",
    ".pub-cache", ".pub/", "migrate_working_dir", ".history", ".svn", ".swiftpm",
    "bin/", "out/", "dist/", "nbproject", ".sts4-cache", ".springBeans",
    ".idea", ".vscode", ".DS_Store", ".flutter-plugins", "flutter_export_environment.sh",
    "-Worktree/", "__pycache__", ".pytest_cache", ".venv", "venv/", ".next/",
    ".turbo", ".cache/", "coverage/",
)


# ── Paths ────────────────────────────────────────────────────────────────

def _toplevel(root: str) -> Path:
    """Normalize to the repo root even if the input is a subfolder. Used as is if not git."""
    p = Path(root).expanduser().resolve()
    try:
        out = subprocess.run(["git", "-C", str(p), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return p


def memory_file(root: Path) -> Path:
    # Built directly instead of via state.KINDS — a single file needs no folder (kind/<repo>/)
    return base_dir() / "worktree" / f"{repo_key(root)}.json"


def _load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


# ── Candidate inventory ───────────────────────────────────────────────────────

def _excluded(rel: str) -> bool:
    # Appending `/` makes folder names like `build` match the `build/` marker
    probe = rel if rel.endswith("/") else rel + "/"
    return any(m in probe for m in EXCLUDE_MARKERS)


def list_candidates(root: Path) -> list[str]:
    """gitignored candidates that actually exist in the original (relative paths, `/` separated).

    Asks git instead of parsing `.gitignore` by hand — subfolder .gitignore files and the
    global excludesfile are judged exactly as git does. A wholly ignored folder appears as one `dir/` line.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--ignored",
             "--exclude-standard", "--directory", "-z"],
            capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    listed = [r for r in out.stdout.decode("utf-8", "replace").split("\0") if r.strip()]
    # `--directory` also emits non-ignored folders (like `.claude/` holding only ignored files)
    # — filter once more with check-ignore to keep only truly ignored entries
    ignored = _check_ignored(root, listed)
    result = []
    for rel in listed:
        if rel not in ignored or _excluded(rel):
            continue
        full = root / rel
        if full.is_file():
            try:
                if full.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
        result.append(rel)
    # If a wholly ignored folder exists, individual entries inside it are duplicates
    dirs = [d for d in result if d.endswith("/")]
    return sorted({r for r in result
                   if not any(r != d and r.startswith(d) for d in dirs)})


def _check_ignored(root: Path, paths: list[str]) -> set[str]:
    if not paths:
        return set()
    try:
        out = subprocess.run(["git", "-C", str(root), "check-ignore", "--stdin", "-z"],
                             input="\0".join(paths).encode("utf-8"),
                             capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return set(paths)  # if it cannot check, do not filter — the agent decides
    # rc=1 when nothing is ignored (not an error)
    if out.returncode not in (0, 1):
        return set(paths)
    return {p for p in out.stdout.decode("utf-8", "replace").split("\0") if p}


def _present(path: str, current: set[str]) -> bool:
    """Does the remembered path still exist in the original. Files inside a wholly ignored folder (`dir/`) count too."""
    return path in current or any(c.endswith("/") and path.startswith(c) for c in current)


def _judged(cand: str, known: set[str]) -> bool:
    """Has the candidate been judged before. A folder candidate counts as judged if a file inside it was judged."""
    return cand in known or (cand.endswith("/") and any(k.startswith(cand) for k in known))


# ── Input validation ───────────────────────────────────────────────────────────

def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _clean(rel: str) -> str | None:
    """Let only relative paths through. Keeps secret values from slipping into the path field."""
    if any(c in rel for c in ("\n", "\r", "\0", "=")):
        return None
    norm = rel.replace("\\", "/")
    keep_dir = norm.endswith("/")
    if norm.startswith("/") or (len(norm) > 1 and norm[1] == ":"):
        return None
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return "/".join(parts) + ("/" if keep_dir else "")


# ── Subcommands ──────────────────────────────────────────────────────────

def cmd_recall(args) -> int:
    root = _toplevel(args.root)
    mem_path = memory_file(root)
    candidates = list_candidates(root)
    mem = _load(mem_path)

    if not mem:
        return emit({
            "ok": True, "verdict": "first_time", "root": str(root),
            "memory_file": str(mem_path), "last": None,
            "candidates": candidates, "new_candidates": candidates,
            "copy_now": [], "gone": [],
            "summary": f"No memory — judge all {len(candidates)} candidates against references/local-files.md",
            "next": "Judge and copy the candidates, then record --root <repo> --copied <a,b> --skipped <c>",
        })

    copied = [p for p in mem.get("copied", []) if isinstance(p, str)]
    skipped = [p for p in mem.get("skipped", []) if isinstance(p, str)]
    current = set(candidates)
    known = set(copied) | set(skipped)
    new = sorted(c for c in current if not _judged(c, known))
    gone = sorted(k for k in known if not _present(k, current))
    copy_now = [p for p in copied if _present(p, current)]

    age_days = None
    try:
        age_days = (date.today() - date.fromisoformat(str(mem.get("date", ""))[:10])).days
    except ValueError:
        pass

    verdict = "changed" if new else "same"
    summary = (f"Copy last set as-is: {len(copy_now)}"
               + (f", judge only {len(new)} new candidates" if new else ", no new candidates")
               + (f", {len(gone)} gone from the source" if gone else ""))
    return emit({
        "ok": True, "verdict": verdict, "root": str(root),
        "memory_file": str(mem_path),
        "last": {"copied": copied, "skipped": skipped, "date": mem.get("date"),
                 "runs": mem.get("runs", 1), "age_days": age_days},
        "candidates": candidates, "new_candidates": new,
        "copy_now": copy_now, "gone": gone,
        "summary": summary,
        "next": "Copy copy_now, judge only new_candidates, then "
                "record --root <repo> --copied <everything copied this time> --skipped <newly skipped>",
    })


def cmd_record(args) -> int:
    root = _toplevel(args.root)
    rejected = []
    copied, skipped = [], []
    for raw, bucket in ([(r, copied) for r in _split(args.copied)]
                        + [(r, skipped) for r in _split(args.skipped)]):
        c = _clean(raw)
        if c is None:
            # A value may have landed in the path field by mistake, so only the first 3 characters are echoed back
            rejected.append(raw[:3] + "…")
        elif c not in bucket:
            bucket.append(c)

    if rejected:
        return emit({
            "ok": False, "code": "bad_path",
            "error": "Only paths relative to the repo root are accepted (absolute paths, `..`, `=` and newlines are rejected)",
            "rejected": rejected,
            "next": "Fix them to relative paths and record again — never pass file contents or values",
        })
    if not copied and not skipped:
        return emit({"ok": False, "code": "empty",
                     "error": "Either --copied or --skipped is required",
                     "next": None})

    mem_path = memory_file(root)
    prev = _load(mem_path) or {}
    current = set(list_candidates(root))
    # This judgement wins; old entries not covered this time carry over only if still in the original
    new_set = set(copied) | set(skipped)
    keep_copied = [p for p in prev.get("copied", []) if p not in new_set and _present(p, current)]
    keep_skipped = [p for p in prev.get("skipped", []) if p not in new_set and _present(p, current)]

    # Do not bloat with repeated records on the same day (memory principle §4)
    same_day = str(prev.get("date", ""))[:10] == date.today().isoformat()
    try:
        prev_runs = int(prev.get("runs", 0))
    except (TypeError, ValueError):
        prev_runs = 0
    data = {
        "schema": SCHEMA,
        "copied": sorted(set(copied) | set(keep_copied)),
        "skipped": sorted(set(skipped) | set(keep_skipped)),
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "runs": max(prev_runs + (0 if same_day else 1), 1),
    }

    mem_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = mem_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, mem_path)  # so an interrupted write leaves no half file

    return emit({
        "ok": True, "memory_file": str(mem_path),
        "copied": data["copied"], "skipped": data["skipped"], "date": data["date"],
        "summary": f"Recorded copy set: copied {len(data['copied'])} · skipped {len(data['skipped'])}",
        "next": None,
    })


def cmd_create(args) -> int:
    return worktree_ops.cmd_create(args, _toplevel)


def cmd_copy(args) -> int:
    return worktree_ops.cmd_copy(args, _toplevel, _split, _clean, memory_file, _load)


def cmd_remove(args) -> int:
    return worktree_ops.cmd_remove(args, _toplevel, memory_file, _load)


# ── argparse ────────────────────────────────────────────────────────────

def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="worktree_cli", description="pro-init-worktree copy-set memory")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("recall", help="Diff between the last copy set and the current candidates")
    p.add_argument("--root", default=".", help="Source repo path (default: current folder)")
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("record", help="Record the set right after copying (paths only)")
    p.add_argument("--root", default=".", help="Source repo path (default: current folder)")
    p.add_argument("--copied", default="", help="Copied relative paths, comma-separated")
    p.add_argument("--skipped", default="", help="Skipped relative paths, comma-separated")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("create", help="Create a worktree from a branch name (branches off --base if missing)")
    p.add_argument("--root", default=".", help="Source repo path (default: current folder)")
    p.add_argument("--branch", required=True, help="Branch name (Korean and # kept as-is)")
    p.add_argument("--base", default=None, help="Ref to branch the new branch from (e.g. origin/develop). Defaults to current HEAD")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("copy", help="Copy the remembered copy set (or --files) into the worktree")
    p.add_argument("--root", default=".", help="Source repo path (default: current folder)")
    p.add_argument("--to", required=True, help="Target worktree path")
    p.add_argument("--files", default="", help="Relative paths to copy, comma-separated (defaults to the remembered set)")
    p.add_argument("--overwrite", action="store_true", help="Overwrite files that already exist in the target")
    p.set_defaults(func=cmd_copy)

    p = sub.add_parser("remove", help="Remove a worktree (refused if there are uncommitted changes)")
    p.add_argument("--root", default=".", help="Source repo path (default: current folder)")
    p.add_argument("--path", default=None, help="Worktree path to remove")
    p.add_argument("--branch", default=None, help="Checked-out branch name (instead of a path)")
    p.add_argument("--force", action="store_true", help="Discard uncommitted changes and remove (only after the user decides)")
    p.set_defaults(func=cmd_remove)
    return parser


def main(argv=None) -> int:
    return run_cli(build_parser(), argv)


if __name__ == "__main__":
    sys.exit(main())
