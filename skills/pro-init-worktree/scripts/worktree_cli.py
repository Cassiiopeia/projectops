#!/usr/bin/env python3
"""worktree_cli — pro-init-worktree 로컬 파일 복사 세트 기억 (#839).

worktree 를 만들 때마다 gitignore 된 로컬 파일 후보를 처음부터 다시 판단하면 토큰이 든다.
레포마다 복사할 세트는 거의 같으므로 **지난번 세트를 기억하고, 달라진 후보만 판단**하게 한다.

    recall --root <레포>                       지난 세트 + 지금 후보와의 차이
    record --root <레포> --copied a,b --skipped c   복사 직후 세트 기록 (경로만)

저장 위치: ~/.projectops/worktree/<owner__repo>.json (기억 원칙 §5 — 로컬 홈, 레포에 커밋되지 않음)
키는 `repo_key` 라서 원본·워크트리 어디서 불러도 같은 기억을 본다.

**파일 내용은 절대 저장하지 않는다.** `.env`·키스토어 같은 비밀 파일이 대상이므로
상대 경로만 남긴다. 값처럼 보이는 입력(절대경로·`..`·줄바꿈·`=`)은 거부한다.

출력: 모든 서브커맨드는 stdout JSON (ok/code/summary/next).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

# Bootstrap — scripts/common import (cwd 무관)
_HERE = Path(__file__).resolve()
_SCRIPTS_ROOT = _HERE.parents[3] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402
from common.emit import emit  # noqa: E402
from common.state import base_dir, repo_key  # noqa: E402

SCHEMA = 1
MAX_BYTES = 1024 * 1024  # 1MB 초과 파일은 설정 파일이 아닐 가능성이 높다 (local-files.md 4-3)

# 재생성 가능한 캐시·빌드 산출물·IDE 상태 — 후보에서 뺀다 (local-files.md 4-2 와 같은 목록 + 파이썬/웹 캐시)
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


# ── 경로 ────────────────────────────────────────────────────────────────

def _toplevel(root: str) -> Path:
    """입력이 하위 폴더여도 레포 루트로 맞춘다. git 이 아니면 그대로 쓴다."""
    p = Path(root).expanduser().resolve()
    try:
        out = subprocess.run(["git", "-C", str(p), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return p


def memory_file(root: Path) -> Path:
    # state.KINDS 에 넣지 않고 직접 조립 — 파일 하나라 폴더(kind/<repo>/)가 필요 없다
    return base_dir() / "worktree" / f"{repo_key(root)}.json"


def _load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


# ── 후보 inventory ───────────────────────────────────────────────────────

def _excluded(rel: str) -> bool:
    # 끝에 `/` 를 붙여 보면 `build` 같은 폴더명도 `build/` 표식에 걸린다
    probe = rel if rel.endswith("/") else rel + "/"
    return any(m in probe for m in EXCLUDE_MARKERS)


def list_candidates(root: Path) -> list[str]:
    """원본에 실제로 있는 gitignored 후보 (상대 경로, `/` 구분).

    `.gitignore` 를 손으로 파싱하지 않고 git 에 묻는다 — 하위 폴더 .gitignore·
    전역 excludesfile 까지 git 과 똑같이 판정된다. 통째로 무시된 폴더는 `dir/` 한 줄로 나온다.
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
    # `--directory` 는 무시되지 않은 폴더(`.claude/` 처럼 안에 무시된 파일만 있는 폴더)도
    # 섞어 내보낸다 — check-ignore 로 한 번 더 걸러 진짜 무시된 것만 남긴다
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
    # 통째로 무시된 폴더가 있으면 그 안의 개별 항목은 중복이다
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
        return set(paths)  # 확인을 못 하면 걸러내지 않는다 — 판단은 agent 가 한다
    # 아무것도 무시되지 않으면 rc=1 이다 (오류 아님)
    if out.returncode not in (0, 1):
        return set(paths)
    return {p for p in out.stdout.decode("utf-8", "replace").split("\0") if p}


def _present(path: str, current: set[str]) -> bool:
    """기억된 경로가 지금도 원본에 있는가. 통째로 무시된 폴더(`dir/`) 안의 파일도 있다고 본다."""
    return path in current or any(c.endswith("/") and path.startswith(c) for c in current)


def _judged(cand: str, known: set[str]) -> bool:
    """후보가 이미 판단된 적 있는가. 폴더 후보는 그 안의 파일을 판단했어도 판단된 것으로 본다."""
    return cand in known or (cand.endswith("/") and any(k.startswith(cand) for k in known))


# ── 입력 검증 ───────────────────────────────────────────────────────────

def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _clean(rel: str) -> str | None:
    """상대 경로만 통과시킨다. 비밀 값이 경로 칸에 섞여 들어오는 것을 막는다."""
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


# ── 서브커맨드 ──────────────────────────────────────────────────────────

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
            "summary": f"기억 없음 — 후보 {len(candidates)}개를 references/local-files.md 기준으로 전부 판단한다",
            "next": "후보를 판단·복사한 뒤 record --root <레포> --copied <a,b> --skipped <c>",
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
    summary = (f"지난 세트 그대로 복사 {len(copy_now)}개"
               + (f", 새 후보 {len(new)}개만 판단" if new else ", 새 후보 없음")
               + (f", 원본에서 사라진 {len(gone)}개" if gone else ""))
    return emit({
        "ok": True, "verdict": verdict, "root": str(root),
        "memory_file": str(mem_path),
        "last": {"copied": copied, "skipped": skipped, "date": mem.get("date"),
                 "runs": mem.get("runs", 1), "age_days": age_days},
        "candidates": candidates, "new_candidates": new,
        "copy_now": copy_now, "gone": gone,
        "summary": summary,
        "next": "copy_now 를 복사하고 new_candidates 만 판단한 뒤 "
                "record --root <레포> --copied <이번에 복사한 전부> --skipped <새로 건너뛴 것>",
    })


def cmd_record(args) -> int:
    root = _toplevel(args.root)
    rejected = []
    copied, skipped = [], []
    for raw, bucket in ([(r, copied) for r in _split(args.copied)]
                        + [(r, skipped) for r in _split(args.skipped)]):
        c = _clean(raw)
        if c is None:
            # 값이 경로 칸에 잘못 들어왔을 수 있으니 되돌려 줄 때도 앞 3글자만 보인다
            rejected.append(raw[:3] + "…")
        elif c not in bucket:
            bucket.append(c)

    if rejected:
        return emit({
            "ok": False, "code": "bad_path",
            "error": "레포 루트 기준 상대 경로만 받는다 (절대경로·`..`·`=`·줄바꿈 거부)",
            "rejected": rejected,
            "next": "상대 경로로 고쳐 다시 record 한다 — 파일 내용·값은 넘기지 않는다",
        })
    if not copied and not skipped:
        return emit({"ok": False, "code": "empty",
                     "error": "--copied 또는 --skipped 중 하나는 있어야 한다",
                     "next": None})

    mem_path = memory_file(root)
    prev = _load(mem_path) or {}
    current = set(list_candidates(root))
    # 이번 판단이 우선, 이번에 다루지 않은 지난 항목은 원본에 아직 있을 때만 이어 간다
    new_set = set(copied) | set(skipped)
    keep_copied = [p for p in prev.get("copied", []) if p not in new_set and _present(p, current)]
    keep_skipped = [p for p in prev.get("skipped", []) if p not in new_set and _present(p, current)]

    # 같은 날 반복 기록으로 부풀리지 않는다 (기억 원칙 §4)
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
    os.replace(tmp, mem_path)  # 쓰다 끊겨도 반쪽 파일이 남지 않게

    return emit({
        "ok": True, "memory_file": str(mem_path),
        "copied": data["copied"], "skipped": data["skipped"], "date": data["date"],
        "summary": f"복사 세트 기록: 복사 {len(data['copied'])}개 · 건너뜀 {len(data['skipped'])}개",
        "next": None,
    })


# ── argparse ────────────────────────────────────────────────────────────

def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="worktree_cli", description="pro-init-worktree 복사 세트 기억")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("recall", help="지난 복사 세트와 지금 후보의 차이")
    p.add_argument("--root", default=".", help="원본 레포 경로 (기본: 현재 폴더)")
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("record", help="복사 직후 세트 기록 (경로만)")
    p.add_argument("--root", default=".", help="원본 레포 경로 (기본: 현재 폴더)")
    p.add_argument("--copied", default="", help="복사한 상대 경로, 쉼표 구분")
    p.add_argument("--skipped", default="", help="건너뛴 상대 경로, 쉼표 구분")
    p.set_defaults(func=cmd_record)
    return parser


def main(argv=None) -> int:
    return run_cli(build_parser(), argv)


if __name__ == "__main__":
    sys.exit(main())
