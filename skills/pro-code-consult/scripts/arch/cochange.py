"""cochange: git 이력 > 함께 바뀌는 파일 (대상별 짝 · 묶음 · 서로 참조 없는 숨은 결합)

판정은 하지 않는다 — 횟수와 비율만 낸다. 같이 고쳐야 했는지는 에이전트가 원문을 보고 정한다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .origins import is_test_path
from .source_files import (MAXIMUM_SOURCE_BYTES, SKIPPED_DIRECTORY_NAMES, is_generated_file, tracked_files,
                           write_outside_repo)

# 기본 읽을 커밋 수
DEFAULT_COMMIT_COUNT = 300
# 이보다 많은 파일을 바꾼 커밋은 일괄 작업(포맷·이동·이름 바꾸기)으로 보고 뺀다
MAXIMUM_FILES_PER_COMMIT = 30
# 짝으로 볼 최소 함께 바뀐 횟수
DEFAULT_MINIMUM_TOGETHER = 3
# 숨은 결합·묶음으로 볼 최소 비율 (함께 바뀐 수 / 둘 중 덜 바뀐 쪽 변경 수)
STRONG_RATIO = 0.5
# 릴리스 자동 커밋 표식 (버전 확정·README 버전 동기화)
SKIPPED_SUBJECT_MARKERS = ("[skip ci]",)
# 거의 모든 변경에 끼는 파일 (짝으로 의미 없음)
NOISE_FILE_NAMES = {"CHANGELOG.md", "CHANGELOG.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                    "pubspec.lock", "poetry.lock", "Podfile.lock", "Cargo.lock", "go.sum", "version.yml"}
# 묶음 하나에 보여 줄 최대 파일 수 (변경 많은 순, 전체 수는 size)
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
    # 테스트 ↔ 운영 짝은 원래 함께 바뀐다 > 숨은 결합 후보에서 뺌
    result["hidden_coupling"] = [p for p in strong_pairs if not any(is_test_path(f) for f in p["files"])
                                 and _is_hidden(root, p["files"])][:limit]
    result["summary"] = (f"{used} commits used, {len(strong_pairs)} strong pairs, "
                         f"{len(result['clusters'])} clusters, {len(result['hidden_coupling'])} hidden couplings shown")
    result["next"] = "Open hidden_coupling pairs and judge whether one change silently depends on the other (references/audit.md)"
    return result


def _read_commits(root: Path, commit_count: int) -> list | None:
    """[(제목, [파일...])] — 실패 시 None"""
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
    """파일별 변경 수, 짝별 함께 바뀐 수 (지금도 추적 중인 파일만, 잡음 커밋·파일 제외)"""
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
    """강한 짝을 이어 묶음 (union-find) > 크기·변경 수 큰 순"""
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
    """두 파일이 서로 이름(확장자 뺀 파일 이름)을 언급하지 않으면 숨은 결합"""
    first, second = files
    return not (_mentions(root / first, Path(second).stem) or _mentions(root / second, Path(first).stem))


def _mentions(path: Path, stem: str) -> bool:
    if len(stem) < 3:
        return True   # 너무 짧은 이름은 판단 불가 > 숨은 결합으로 올리지 않음
    try:
        if path.stat().st_size > MAXIMUM_SOURCE_BYTES:
            return True
        return stem in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
