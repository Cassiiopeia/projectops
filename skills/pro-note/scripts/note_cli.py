#!/usr/bin/env python3
"""note_cli — pro-note skill 전용 CLI.

알아낸 것을 기록하고, 막혔을 때 과거 기록을 찾아온다.

서브커맨드:
  search          기록 검색 (저장소 + 홈 양쪽)
  resolve-scope   저장 위치 판정 (프로젝트 / 홈)
  get-output-path 기록 파일 경로 계산
  list            기록 목록

설계 메모:
  검색이 이 스킬의 핵심이다. 기록은 검색을 위한 재료일 뿐이며,
  막혔을 때 과거를 꺼내오지 못하면 쌓아둔 것이 의미가 없다.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.emit import emit  # noqa: E402
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402

# 기록 종류 — case는 사건, fact는 재사용 가능한 사실
KINDS = ("case", "fact")

# 홈 기록 루트. 프로젝트를 옮겨 다녀도 따라오는 지식이 여기 쌓인다.
HOME_ROOT = Path.home() / ".projectops" / "note"


# ===================================================================
# 경로 해석
# ===================================================================

def _git(args: list[str], cwd: Path | None = None) -> str | None:
    """git 명령 실행 후 stdout 반환. 실패하면 None.

    encoding·errors를 반드시 지정한다 — Windows에서 text=True만 쓰면 시스템
    기본 인코딩(cp949)으로 디코딩을 시도해, 한글 파일명이 목록에 있으면
    UnicodeDecodeError로 죽는다. 이 저장소처럼 한글 파일명을 쓰면 바로 터진다.
    """
    try:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
            cwd=str(cwd) if cwd else None,
        )
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def _repo_root(start: Path | None = None) -> Path | None:
    """git 저장소 루트. 저장소 밖이면 None."""
    out = _git(["rev-parse", "--show-toplevel"], start)
    return Path(out.strip()) if out and out.strip() else None


def _project_note_root(project_root: Path) -> Path:
    """저장소 안 기록 루트. 산출물 루트 설정(output.root)을 그대로 따른다."""
    try:
        from common.paths import resolve_output_root
        return Path(resolve_output_root(project_root)) / "note"
    except Exception:
        return project_root / "docs" / "projectops" / "note"


def _roots(project_root: Path | None) -> list[tuple[str, Path]]:
    """검색 대상 루트 목록. (scope, path) 쌍."""
    roots: list[tuple[str, Path]] = []
    if project_root:
        roots.append(("project", _project_note_root(project_root)))
    roots.append(("home", HOME_ROOT))
    return roots


# ===================================================================
# search — 이 스킬의 핵심
# ===================================================================

def _tokenize(query: str) -> list[str]:
    """검색어를 토큰으로 쪼갠다. 2글자 미만은 잡음이라 버린다."""
    parts = re.split(r"[\s,./:;_\-\[\]()]+", query.lower())
    return [p for p in parts if len(p) >= 2]


def _score(text: str, tokens: list[str]) -> int:
    """토큰이 몇 개나 등장하는지로 점수를 낸다.

    형태소 분석 없이 부분 문자열 일치만 본다. 한국어·영어가 섞이고
    표현이 매번 다른 기록에서는 이 정도가 오히려 안정적이다.
    """
    low = text.lower()
    return sum(1 for t in tokens if t in low)


def _iter_notes(root: Path):
    for kind in KINDS:
        d = root / f"{kind}s"
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md"), reverse=True):
            yield kind, f


def cmd_search(args) -> int:
    tokens = _tokenize(args.query)
    if not tokens:
        return emit({"ok": False, "code": "empty_query",
                     "summary": "검색어가 비었습니다"})

    project_root = _repo_root()
    hits = []
    for scope, root in _roots(project_root):
        for kind, path in _iter_notes(root):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            # 제목(파일명)은 본문보다 신뢰도가 높아 가중치를 준다
            s = _score(path.stem, tokens) * 3 + _score(text, tokens)
            if s <= 0:
                continue
            title = next((l.lstrip("# ").strip() for l in text.split("\n")
                          if l.startswith("# ")), path.stem)
            hits.append({
                "scope": scope, "kind": kind, "title": title,
                "path": str(path), "score": s,
            })

    hits.sort(key=lambda h: h["score"], reverse=True)
    hits = hits[: args.limit]

    if not hits:
        return emit({
            "count": 0, "hits": [],
            "summary": f'"{args.query}" 관련 기록 없음 — 처음 겪는 문제로 보입니다',
            "next": "조사를 진행하고, 어렵게 풀렸다면 기록을 남기세요",
        })
    return emit({
        "count": len(hits), "hits": hits,
        "summary": f'"{args.query}" 관련 기록 {len(hits)}건 발견',
        "next": "가장 점수가 높은 기록을 먼저 읽고 그 해결법이 적용되는지 확인하세요",
    })


# ===================================================================
# resolve-scope — 저장 위치 자동 판정
# ===================================================================

def _changed_files(project_root: Path) -> list[str]:
    """작업 트리에서 변경된 파일. 커밋 전후 모두 잡히도록 두 소스를 합친다.

    `-c core.quotepath=false`가 없으면 git이 한글 파일명을 \\352\\270\\260 형태로
    이스케이프해 사용자에게 그대로 노출된다.
    """
    files: set[str] = set()
    for args in (["-c", "core.quotepath=false", "status", "--porcelain"],
                 ["-c", "core.quotepath=false", "diff", "--name-only", "HEAD~1..HEAD"]):
        out = _git(args, project_root)
        if not out:
            continue
        is_status = "status" in args
        for line in out.splitlines():
            line = line.rstrip()
            if not line:
                continue
            # porcelain은 앞 2칸이 상태 코드 + 공백
            name = line[3:] if is_status else line
            files.add(name.strip().strip('"'))
    return sorted(f for f in files if f)


def cmd_resolve_scope(args) -> int:
    """저장 위치를 판정한다.

    핵심 신호는 "저장소 파일이 바뀌었는가"다. 바뀌었으면 이 프로젝트
    고유 문제이고, 안 바뀌었으면 도구·환경 쪽 문제일 가능성이 높다.
    확실할 때는 묻지 않고, 애매할 때만 agent가 사용자에게 확인한다.
    """
    project_root = _repo_root()
    if not project_root:
        return emit({
            "scope": "home", "confidence": "certain",
            "reason": "git 저장소 밖이라 프로젝트에 귀속시킬 수 없습니다",
            "ask_user": False,
            "summary": "홈에 저장",
        })

    changed = _changed_files(project_root)
    if args.scope:  # 사용자가 명시하면 그대로 따른다
        return emit({
            "scope": args.scope, "confidence": "certain",
            "reason": "사용자가 직접 지정했습니다",
            "ask_user": False, "summary": f"{args.scope}에 저장",
        })

    if changed:
        return emit({
            "scope": "project", "confidence": "certain",
            "reason": f"이 저장소 파일 {len(changed)}개가 변경되었습니다",
            "changed_files": changed[:10],
            "ask_user": False,
            "summary": "프로젝트에 저장",
            "next": "get-output-path --scope project",
        })

    return emit({
        "scope": "home", "confidence": "likely",
        "reason": "저장소 파일 변경이 없어 도구·환경 쪽 문제로 보입니다",
        "ask_user": True,
        "summary": "홈으로 판정 (애매하면 사용자 확인)",
        "next": "홈에 저장할지 이 저장소에만 남길지 한 번 확인하세요",
    })


# ===================================================================
# get-output-path / list
# ===================================================================

def _slugify(title: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "_", (title or "").strip())
    return re.sub(r"_+", "_", s).strip("_")[:60] or "untitled"


def cmd_get_output_path(args) -> int:
    if args.kind not in KINDS:
        return emit({"ok": False, "code": "bad_kind",
                     "summary": f"kind는 {' 또는 '.join(KINDS)}여야 합니다"})

    project_root = _repo_root()
    if args.scope == "project":
        if not project_root:
            return emit({"ok": False, "code": "not_a_repo",
                         "summary": "git 저장소가 아니라 프로젝트에 저장할 수 없습니다"})
        root = _project_note_root(project_root)
    else:
        root = HOME_ROOT

    d = root / f"{args.kind}s"
    slug = _slugify(args.title)

    if args.kind == "fact":
        # fact는 주제별로 갱신되므로 날짜를 붙이지 않는다
        path = d / f"{slug}.md"
    else:
        today = date.today().strftime("%Y%m%d")
        n = sum(1 for f in d.glob(f"{today}_*.md")) + 1 if d.exists() else 1
        path = d / f"{today}_{n:03d}_{slug}.md"

    return emit({
        "path": str(path), "dir": str(d), "scope": args.scope,
        "kind": args.kind, "exists": path.exists(),
        "summary": f"{args.scope}/{args.kind} 경로 계산 완료",
        "next": "디렉터리를 만든 뒤 이 경로에 기록을 저장하세요",
    })


def cmd_list(args) -> int:
    project_root = _repo_root()
    items = []
    for scope, root in _roots(project_root):
        if args.scope and scope != args.scope:
            continue
        for kind, path in _iter_notes(root):
            items.append({"scope": scope, "kind": kind,
                          "title": path.stem, "path": str(path)})
    return emit({
        "count": len(items), "items": items[: args.limit],
        "summary": f"기록 {len(items)}건",
    })


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="note_cli", description="pro-note skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="기록 검색 (저장소 + 홈)")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("resolve-scope", help="저장 위치 판정")
    p.add_argument("--scope", choices=["project", "home"], help="직접 지정 시")
    p.set_defaults(func=cmd_resolve_scope)

    p = sub.add_parser("get-output-path", help="기록 파일 경로 계산")
    p.add_argument("kind", choices=list(KINDS))
    p.add_argument("--title", required=True)
    p.add_argument("--scope", choices=["project", "home"], default="project")
    p.set_defaults(func=cmd_get_output_path)

    p = sub.add_parser("list", help="기록 목록")
    p.add_argument("--scope", choices=["project", "home"])
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_list)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
