"""`tidy` — 기본은 흩어진 기억 통합(예전 동작). `tidy --buckets` 가 쌓인 상태 보고 · --apply 때만 정리 (#932).

--buckets 가 보는 것 4개: 버킷(크기·최근 사용·가짜/임시·고아 프로필), Maestro 테스트 출력(~/.maestro/tests),
projectops tmp, 낡은 기억. 기본은 보고만(dry). 지우는 것은 --apply 일 때 아래뿐이다.
  · 가짜/임시 버킷 중 --days 일 넘게 안 쓴 것 (데이터 파일이 든 것은 남긴다)
  · 상태 파일 없이 프로필만 남은 버킷의 프로필 (--days 일 넘게 안 쓴 것)
  · --days 일 넘은 Maestro 테스트 폴더 · projectops tmp 항목
  · 낡은 기억 표 적용 (대체 표시 · 테스트 오염 삭제)
브라우저 프로세스가 살아 있거나 쓰는 중으로 보이는 프로필은 절대 지우지 않는다.
실제 레포(owner__repo 키 · 알려진 로컬 레포) 버킷은 프로필도 데이터도 지우지 않고 크기·나이만 보고한다.
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
from pro_launch.runtime.output import out
from pro_launch.runtime.procs import pid_alive, process_command_lines
from pro_launch.runtime.recent_roots import load_recent_roots

SECONDS_PER_DAY = 86400
DEFAULT_IDLE_DAYS = 7
# <owner>__<repo> — git remote 에서 나온 정상 레포 키
REPO_KEY_PATTERN = re.compile(r"^[^/_][^/]*__[^/]+$")
# 버킷으로 보지 않는 폴더 (기계 공용 · 세션 중계 · 가상환경) + 한 단계 더 들어가 보는 _scratch
RESERVED_NAMES = (MACHINE_BUCKET, SCRATCH_BUCKET, "maestro-sessions", ".venv")
PROFILE_NAME = ".browser-profile"
# 이 파일이 있으면 지워도 되는 임시 폴더가 아니다 (사람·agent 가 남긴 데이터)
DATA_FILES = ("access.json", "learned.json", "devices.json", "journal.json", "app-map.json")
BROWSER_STATE_FILE = "browser.json"


def _tree_size(path: Path) -> int:
    """폴더 전체 바이트 (링크는 따라가지 않는다). 읽지 못하는 것은 건너뛴다."""
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
    """폴더와 바로 아래 항목의 가장 최근 수정 시각 (프로필 내부는 보지 않는다)."""
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
    """사람이 남긴 데이터(접속 방법 · 기억 · 자리 기록)가 있나."""
    if any((path / name).exists() for name in DATA_FILES):
        return True
    return bool(knowledge.load(path / knowledge.FILE))


def _live_browser_pid(path: Path) -> int | None:
    """browser.json 의 pid 가 살아 있으면 그 pid."""
    try:
        pid = int(json.loads((path / BROWSER_STATE_FILE).read_text(encoding="utf-8")).get("pid") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return pid if pid and pid_alive(pid) else None


def _is_profile_in_use(profile: Path, command_lines: str | None) -> bool:
    """이 프로필을 쓰는 프로세스가 있나. 프로세스 목록을 못 읽으면 쓰는 중으로 본다."""
    return True if not command_lines else str(profile) in command_lines


def _known_folder_names() -> set[str]:
    """최근 루트(레포)의 폴더 이름 — 원격 없는 로컬 레포의 버킷 이름과 대조한다."""
    return {Path(row["path"]).name for row in load_recent_roots()}


def _classify(parent_name: str, name: str, known_names: set[str]) -> str:
    """real(원격 키 · 알려진 로컬 레포) | scratch(_scratch 아래) | fake(그 밖의 폴더 이름)."""
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
                # 상태(데이터) 없이 프로필만 남은 버킷의 프로필
                "is_orphan_profile": has_profile and not _bucket_has_data(path),
                "is_browser_alive": live_pid is not None or (has_profile and _is_profile_in_use(profile, command_lines)),
            })
    return rows


def _decide_bucket_action(row: dict, idle_days: float) -> str:
    """버킷 한 건의 처리: delete_bucket | delete_profile | keep (이유는 skipped_reason)."""
    if row["is_browser_alive"]:
        return "keep:browser_alive"
    # 실제 레포는 로그인 프로필도 사용자 자산이다 — 보고만 한다
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
            return out({"ok": False, "code": "bad_args", "error": "--apply 는 --buckets 와 함께 쓴다",
                        "next": "tidy --buckets [--apply] [--days N]"})
        merged = knowledge.tidy()
        return out({"ok": True, "code": "ok", **merged,
                    "summary": f"{merged['moved_to_machine']}건을 이 컴퓨터 범위로 옮김 (합친 것 {merged['merged']}건)",
                    "next": "recall --scope machine  # 결과를 본다"})
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
    summary = (f"{len(removed)}건 정리함" if args.apply else
               f"버킷 {len(buckets)}개 {total_mb}MB · 정리 후보 {len(deletable)}개 · Maestro {maestro['count']}개 "
               f"{maestro['size_mb']}MB (보고만 — 지우려면 --apply)")
    return out({"ok": True, "code": "ok", "mode": "apply" if args.apply else "dry", "idle_days": args.days,
                "buckets": sorted(buckets, key=lambda r: -r["size_mb"]), "total_mb": total_mb,
                "maestro_tests": {k: v for k, v in maestro.items() if k != "_old"},
                "projectops_tmp": {k: v for k, v in tmp.items() if k != "_old"},
                "stale_knowledge": stale_knowledge, "removed": removed, "skipped": skipped,
                "summary": summary,
                "next": ("tidy --buckets --apply  # 정리 후보(action: delete_*)와 오래된 Maestro 출력만 지운다"
                         if not args.apply and (deletable or maestro["old_count"]) else None)})


def configure_tidy(p) -> None:
    p.add_argument("--buckets", action="store_true",
                   help="기억 통합 대신 쌓인 상태(버킷 · 프로필 · Maestro 출력 · tmp · 낡은 기억)를 보고한다")
    p.add_argument("--apply", action="store_true", help="--buckets 와 함께: 보고만 하지 않고 정리한다")
    p.add_argument("--days", type=float, default=DEFAULT_IDLE_DAYS,
                   help=f"이 일수보다 오래 안 쓴 것만 정리 대상 (기본 {DEFAULT_IDLE_DAYS})")
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="tidy", help="흩어진 기억 정리 (--buckets: 쌓인 상태 보고 · --apply 때만 정리)",
            run=cmd_tidy, configure=configure_tidy),
]
