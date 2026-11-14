"""cochange: git history > files that change together (pairs per target, clusters, hidden coupling without mutual references)

No verdicts — only counts and ratios. The agent reads the source to decide whether they had to change together.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .origins import is_test_path
from .source_files import (MAXIMUM_SOURCE_BYTES, SKIPPED_DIRECTORY_NAMES, is_generated_file, tracked_files,
                           write_outside_repo)

# Default number of commits to read
DEFAULT_COMMIT_COUNT = 300
# Commits touching more files than this are bulk work (format, move, rename) and are skipped
MAXIMUM_FILES_PER_COMMIT = 30
# Minimum co-change count to count as a pair
DEFAULT_MINIMUM_TOGETHER = 3
# Minimum ratio for hidden coupling and clusters (co-changes / changes of the less-changed file)
STRONG_RATIO = 0.5
# Automated release commit markers (version finalize, README version sync)
SKIPPED_SUBJECT_MARKERS = ("[skip ci]",)
# Files present in almost every change (meaningless as pairs)
NOISE_FILE_NAMES = {"CHANGELOG.md", "CHANGELOG.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                    "pubspec.lock", "poetry.lock", "Podfile.lock", "Cargo.lock", "go.sum", "version.yml"}
# Max files shown per cluster (most-changed first; the full count is size)
MAXIMUM_CLUSTER_FILES_SHOWN = 8
RECORD_SEPARATOR = "\x1e"


def analyze_cochange(root: Path, targets: list, commit_count: int, minimum_together: int, limit: int,
                     out: str | None = None) -> dict:
    commits = _read_commits(root, commit_count)
    if commits is None:
        return {"ok": False, "code": "git_failed", "summary": "git log failed",
                "next": "Run inside a git repository with history"}
    existing = set(tracked_files(root))
    change_counts, pair_counts, used = _count(commits, existing)
    result = {"commits_read": len(commits), "commits_used": used,
              "excluded_rule": f"merges, [skip ci], commits touching more than {MAXIMUM_FILES_PER_COMMIT} files, lock and changelog files"}
    if out:
        written = write_outside_repo(root, out, {"change_counts": change_counts,
                                                 "pairs": [{"files": list(k), "together": v} for k, v in pair_counts.items()]})
        if written.get("ok") is False:
            return written
        result["out"] = written
    if targets:
        result["targets"] = [_partners(root, target, change_counts, pair_counts, minimum_together, limit)
                             for target in targets]
        unchanged = [t["target"] for t in result["targets"] if not t["changes"]]
        result["summary"] = (f"{len(targets)} target(s), {used} commits used"
                             + (f"; no history for {', '.join(unchanged)}" if unchanged else ""))
        result["next"] = ("Put partners that this change does not touch into the proposal scope (or say why not), "
                          "then pass them to the reviewer (references/refactor.md)")
        return result
    strong_pairs = _strong_pairs(change_counts, pair_counts, minimum_together)
    result["clusters"] = _clusters(strong_pairs, change_counts)[:limit]
    # Test ↔ production pairs naturally change together > excluded from hidden-coupling candidates
    result["hidden_coupling"] = [p for p in strong_pairs if not any(is_test_path(f) for f in p["files"])
                                 and _is_hidden(root, p["files"])][:limit]
    result["summary"] = (f"{used} commits used, {len(strong_pairs)} strong pairs, "
                         f"{len(result['clusters'])} clusters, {len(result['hidden_coupling'])} hidden couplings shown")
    result["next"] = "Open hidden_coupling pairs and judge whether one change silently depends on the other (references/audit.md)"
    return result


def _read_commits(root: Path, commit_count: int) -> list | None:
    """[(subject, [files...])] — None on failure"""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "-c", "core.quotePath=false", "log", "--no-merges", f"-n{commit_count}", "--name-only", "--relative",
             f"--format={RECORD_SEPARATOR}%s"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    commits = []
    for record in completed.stdout.split(RECORD_SEPARATOR)[1:]:
        lines = [line.strip() for line in record.splitlines()]
        commits.append((lines[0] if lines else "", [line for line in lines[1:] if line]))
    return commits


def _count(commits: list, existing: set):
    """Change count per file and co-change count per pair (only files still tracked; noise commits and files excluded)"""
    change_counts, pair_counts, used = {}, {}, 0
    for subject, files in commits:
        if any(marker in subject for marker in SKIPPED_SUBJECT_MARKERS) or len(files) > MAXIMUM_FILES_PER_COMMIT:
            continue
        kept = sorted({f for f in files if f in existing and _is_meaningful(f)})
        if not kept:
            continue
        used += 1
        for index, first in enumerate(kept):
            change_counts[first] = change_counts.get(first, 0) + 1
            for second in kept[index + 1:]:
                pair_counts[(first, second)] = pair_counts.get((first, second), 0) + 1
    return change_counts, pair_counts, used


def _is_meaningful(relative: str) -> bool:
    parts = relative.split("/")
    return (parts[-1] not in NOISE_FILE_NAMES and not is_generated_file(relative)
            and not (set(parts[:-1]) & SKIPPED_DIRECTORY_NAMES))


def _partners(root: Path, target: str, change_counts: dict, pair_counts: dict, minimum_together: int, limit: int) -> dict:
    target = Path(target).as_posix().removeprefix("./")
    changes = change_counts.get(target, 0)
    partners = []
    for (first, second), together in pair_counts.items():
        if target not in (first, second) or together < minimum_together:
            continue
        other = second if first == target else first
        partners.append({"file": other, "together": together, "ratio": round(together / changes, 2),
                         "is_referenced": not _is_hidden(root, (target, other))})
    partners.sort(key=lambda p: (-p["together"], p["file"]))
    return {"target": target, "changes": changes, "partners": partners[:limit],
            "truncated": max(0, len(partners) - limit)}


def _strong_pairs(change_counts: dict, pair_counts: dict, minimum_together: int) -> list:
    pairs = []
    for (first, second), together in pair_counts.items():
        if together < minimum_together:
            continue
        ratio = together / min(change_counts[first], change_counts[second])
        if ratio >= STRONG_RATIO:
            pairs.append({"files": [first, second], "together": together, "ratio": round(ratio, 2)})
    pairs.sort(key=lambda p: (-p["together"], -p["ratio"]))
    return pairs


def _clusters(strong_pairs: list, change_counts: dict) -> list:
    """Join strong pairs into clusters (union-find) > largest size and change count first"""
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for pair in strong_pairs:
        first, second = pair["files"]
        parent[find(first)] = find(second)
    groups = {}
    for node in list(parent):
        groups.setdefault(find(node), []).append(node)
    clusters = [{"size": len(files), "files": sorted(files, key=lambda f: -change_counts[f])[:MAXIMUM_CLUSTER_FILES_SHOWN],
                 "changes": sum(change_counts[f] for f in files)}
                for files in groups.values() if len(files) > 2]
    clusters.sort(key=lambda c: (-c["size"], -c["changes"]))
    return clusters


def _is_hidden(root: Path, files) -> bool:
    """Hidden coupling when neither file mentions the other's name (file name without extension)"""
    first, second = files
    return not (_mentions(root / first, Path(second).stem) or _mentions(root / second, Path(first).stem))


def _mentions(path: Path, stem: str) -> bool:
    if len(stem) < 3:
        return True   # names too short to judge > not reported as hidden coupling
    try:
        if path.stat().st_size > MAXIMUM_SOURCE_BYTES:
            return True
        return stem in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
