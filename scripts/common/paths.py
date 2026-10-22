"""산출물 md 파일 경로를 계산한다."""

import os
import re
from pathlib import Path
from typing import Optional, Union


def get_next_seq(skill_dir: Path, today: str, strict: bool = False,
                 title: Optional[str] = None) -> str:
    """
    skill_dir 내에서 오늘 날짜(today)로 시작하는 파일 개수 + 1을 3자리로 반환한다.
    title을 주면 오늘 같은 제목 산출물(파일·폴더)의 번호를 재사용한다 (재호출마다 새 폴더가 생기지 않게, #971).

    strict=True이면 skill_dir이 존재하지 않을 때 FileNotFoundError를 던진다.
    CLI 레이어가 잘못된 skill_id를 명시적으로 거부할 때 사용한다.
    """
    if not skill_dir.exists():
        if strict:
            raise FileNotFoundError(f"skill_dir does not exist: {skill_dir}")
        return "001"
    today_names = [f.name for f in skill_dir.iterdir() if f.name.startswith(today)]
    reused = _find_same_title_seq(today_names, today, title) if title else None
    return reused or f"{len(today_names) + 1:03d}"


def _find_same_title_seq(today_names: list, today: str, title: str) -> Optional[str]:
    """오늘 같은 제목 산출물 > 그 일련번호 (`{날짜}_{NNN}_{제목}` 폴더 또는 `.md`)

    일련번호 범위(오늘 항목 수 이하)만 재사용 — 등록 후 실제 이슈 번호로 바꾼 문서(`_245_`)는 덮지 않는다.
    """
    pattern = re.compile(rf"^{today}_(\d{{3}})_{re.escape(title)}(?:\.md)?$")
    for name in sorted(today_names):
        matched = pattern.match(name)
        if matched and int(matched.group(1)) <= len(today_names):
            return matched.group(1)
    return None


def _drop_repeated_issue_number(title: str, issue_number: Optional[str]) -> str:
    """제목 앞의 같은 이슈 번호 제거: `574_제목`·`20261021_574_제목` + 574 > `제목` (경로 `574_574_` 방지)"""
    if not issue_number:
        return title
    stripped = re.sub(rf"^(?:\d{{8}}_)?{re.escape(issue_number)}_", "", title)
    return stripped or title


def build_output_path(
    base_dir: Union[str, Path],
    skill_id: str,
    today: str,
    number: str,
    title: str,
) -> Path:
    """최종 산출물 경로를 반환한다."""
    return Path(base_dir) / skill_id / f"{today}_{number}_{title}.md"


# ===================================================================
# 산출물 경로 해석 (#525) — Layer 1 단일 구현
# ===================================================================
# 과거에는 report/review 등 여러 CLI가 같은 로직을 각자 복사해 갖고 있었고,
# 나머지 산출물 스킬은 계산 수단조차 없어 "agent가 직접 계산"하는 상태였다. 규칙이 코드로
# 강제되지 않으니 스킬마다 파일명이 갈라져도 알아챌 방법이 없었다.
# 이 함수가 유일한 구현이며, 모든 스킬 CLI는 이것을 호출한다.

DEFAULT_OUTPUT_ROOT = "docs/projectops"


def resolve_output_root(project_root: Union[str, Path]) -> Path:
    """산출물 루트를 결정한다. 설정이 없으면 기존 위치를 그대로 쓴다.

    설정(config.json)의 `output.root` 로 팀마다 다른 위치를 쓸 수 있다.
    - 상대경로면 저장소 루트 기준 (예: "docs/dev" → <repo>/docs/dev)
    - 절대경로면 그대로 (저장소 밖에 모으고 싶을 때)
    - 미설정이면 docs/projectops — 즉 설정을 건드리지 않으면 동작이 바뀌지 않는다
    """
    return _join_output_root(project_root, read_configured_output_root()[0])


def read_configured_output_root() -> tuple[str, Optional[str]]:
    """config.json 의 output.root > (값, 경고). 못 쓰는 설정이면 빈 값(기본 위치) + 무엇이 문제인지"""
    from common.config import config_path, load_with_status
    try:
        data, status = load_with_status()
        location = config_path()
    except OSError as error:   # 옛 경로 이주 복사 실패 등
        return "", f"could not open config.json; ignoring output.root and using the default location ({DEFAULT_OUTPUT_ROOT}): {error}"
    if status == "unreadable":
        return "", (f"config.json is broken (JSON syntax or encoding); ignoring output.root and "
                    f"using the default location ({DEFAULT_OUTPUT_ROOT}): {location}")
    if not isinstance(data, dict):
        return "", None
    output = data.get("output")
    if output is None:
        return "", None
    configured = output.get("root") if isinstance(output, dict) else None
    if not isinstance(output, dict) or not isinstance(configured, (str, type(None))):
        return "", f"output.root in config.json is not a string; using the default location ({DEFAULT_OUTPUT_ROOT})"
    return (configured or "").strip(), None


def _join_output_root(project_root: Union[str, Path], configured: str) -> Path:
    """설정값 > 산출물 루트 (빈 값이면 기본, 상대경로면 저장소 기준)"""
    root = Path(project_root)
    if not configured:
        return root / DEFAULT_OUTPUT_ROOT
    p = Path(configured).expanduser()
    return p if p.is_absolute() else root / p


# ===================================================================
# 추적 제외 (#621) — 증거물은 저장소에 쌓이면 안 된다
# ===================================================================
# 스킬 산출물은 두 종류다. 섞으면 한쪽이 반드시 틀린다.
#
#   문서  — 사람이 읽고 이슈에서 참조한다. **추적해야 한다.**
#           보고서·계획·분석·리뷰·이슈·테스트케이스 …
#   증거  — 스크린샷·화면 덤프·렌더·차이 그림. 재생성되고 무겁다.
#           **추적하면 안 된다.** 실측으로 한 레포의 agent-test 가 9.3MB였다.
#
# 폴더가 스스로 제외 규칙을 들고 다니게 한다 (#561 과 같은 방식) — 레포 루트
# .gitignore 를 건드리면 다른 세션·다른 도구의 규칙과 충돌한다.
#
# **새 산출물 스킬을 만들면 아래 집합에 반드시 넣는다.** 빠뜨리면 증거물이
# 조용히 커밋되기 시작하고, 알아챌 때쯤엔 이미 이력에 박혀 있다.
EVIDENCE_SKILLS = frozenset({
    "agent-test",     # 스크린샷·기기 로그
    # 덤프·시안 export·앱 렌더·차이 그림. #854 에서 figma-verify → figma 로 이름을 바꿨다.
    # 옛 figma-verify/ 폴더는 그대로 둔다 — 회차마다 새로 만드는 증거물이라 다시 읽는 곳이 없고,
    # 스스로 .gitignore 를 들고 있어 커밋되지도 않는다. 그래서 읽기 폴백을 두지 않는다.
    "figma",
    "launch",         # 앱·웹 캡처 · http 응답 (#629)
    "design-brief",   # 요청서 보드 · 상태별 캡처 (#634)
})

# 사라진 스킬(note·analyze·plan·implement·design-analyze·refactor-analyze·ppt·troubleshoot·pr)은 뺐다 (#822).
# 남겨 두면 없는 스킬 이름으로도 산출물 폴더가 만들어진다.
DOCUMENT_SKILLS = frozenset({
    "issue", "oss-consult", "report", "review", "testcase",
})


def gitignore_body(skill_id: str) -> str:
    return (f"# {skill_id} 증거물은 추적하지 않는다 (#621)\n"
            "# 이 폴더는 재생성되는 산출물만 담는다 — 저장소에 쌓이면 안 된다.\n"
            "*\n!.gitignore\n")


def ensure_untracked(dir_path: Union[str, Path], skill_id: str) -> str:
    """폴더가 스스로 추적 제외를 들고 다니게 한다.

    반환: created(새로 씀) / already(우리 것이 이미 있음) / kept(남의 것 보존)
    **남이 쓴 .gitignore 는 절대 덮지 않는다.**
    """
    d = Path(dir_path)
    d.mkdir(parents=True, exist_ok=True)
    f = d / ".gitignore"
    body = gitignore_body(skill_id)
    if f.exists():
        if f.is_file() and f.read_text(encoding="utf-8") == body:
            return "already"
        return "kept"
    f.write_text(body, encoding="utf-8")
    return "created"


def add_root_and_issue_args(parser, with_issue: bool = True) -> None:
    """get-output-path 공통 인자: --root(프로젝트), --issue(이슈 번호 직접 지정) (#943)"""
    parser.add_argument("--root", default=None,
                        help="project root (default: $PROJECT_ROOT, then the git root of the current folder)")
    if with_issue:
        parser.add_argument("--issue", type=int, default=None,
                            help="issue number to use (default: found from the worktree path, then the branch name)")


def _project_dir(root: Optional[str]) -> Optional[str]:
    """프로젝트 폴더: --root > $PROJECT_ROOT > None(=현재 폴더). 없는 폴더면 None 대신 ValueError"""
    chosen = root or os.environ.get("PROJECT_ROOT") or None
    if chosen and not os.path.isdir(chosen):
        raise ValueError(chosen)
    return chosen


def resolve_output_path(skill_id: str, forced_title: Optional[str] = None,
                        use_issue_number: bool = True,
                        root: Optional[str] = None, issue: Optional[int] = None) -> dict:
    """산출물 md 경로를 계산해 dict로 반환한다 (CLI가 그대로 emit한다).

    이슈 번호는 worktree 경로 → 브랜치명 순으로 찾고, 둘 다 없으면
    그날의 일련번호를 붙인다. 제목은 인자 우선, 없으면 경로에서 추출한다.

    root: 프로젝트 루트. 없으면 $PROJECT_ROOT, 그다음 현재 폴더 (셸 폴더가 바뀐 뒤에도 맞게, #943).
    issue: 이슈 번호를 직접 지정 (worktree·브랜치에서 찾은 값보다 우선).

    use_issue_number=False 면 브랜치·worktree 번호를 쓰지 않고 일련번호만 붙인다.
    새 이슈 문서처럼 **아직 번호가 없는 산출물**이 지금 브랜치의 이슈 번호를
    빌려 가면 다른 이슈 파일과 이름이 겹친다 (#822).
    """
    import subprocess
    from datetime import date

    # 등록된 스킬만 받는다. `../../escape` 같은 값이 산출물 루트 밖으로 나가는 것을 막는다 (#713)
    if skill_id not in EVIDENCE_SKILLS and skill_id not in DOCUMENT_SKILLS:
        return {
            "ok": False,
            "code": "unknown_skill_id",
            "error": f"unregistered skill_id: {skill_id!r}",
            "known": sorted(EVIDENCE_SKILLS | DOCUMENT_SKILLS),
            "hint": "for a new output skill, register it in EVIDENCE_SKILLS/DOCUMENT_SKILLS in scripts/common/paths.py",
        }

    from common.issue_number import (
        extract_from_path as in_extract_from_path,
        extract_from_branch, get_current_branch, resolve,
    )
    from common.gh_branch import strip_issue_decorations
    from common.title import normalize, extract_from_path as title_extract_from_path

    try:
        project_dir = _project_dir(root)
    except ValueError as bad:
        return {"ok": False, "code": "root_not_found", "error": f"project folder not found: {bad}",
                "next": "pass a real project path to --root"}
    cwd = project_dir or os.getcwd()
    today = date.today().strftime("%Y%m%d")

    wt_number = in_extract_from_path(cwd)
    branch = get_current_branch(project_dir)
    br_number = extract_from_branch(branch) if branch else None
    issue_num, mismatch = resolve(wt_number, br_number)
    if issue is not None:
        issue_num, mismatch = str(issue), False
    if not use_issue_number:
        issue_num, mismatch = None, False

    try:
        root_str = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=project_dir, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"ok": False, "code": "git_not_found", "error": "not a git repository",
                "next": "run it from the project folder or pass --root <project path> ($PROJECT_ROOT also works)"}

    configured_root, config_warning = read_configured_output_root()
    output_base = _join_output_root(root_str, configured_root)
    skill_dir = output_base / skill_id
    # 제목 정리 (이모지·[태그] 제거 > 파일명 정규화 > 앞의 같은 이슈 번호 제거)
    if forced_title:
        final_title = normalize(strip_issue_decorations(forced_title))
    else:
        raw = title_extract_from_path(cwd)
        final_title = normalize(raw) if raw else "untitled"
    final_title = _drop_repeated_issue_number(final_title, issue_num)

    # 번호: 이슈 번호 > 오늘 같은 제목의 일련번호 재사용(증거물만) > 새 일련번호
    # 문서(issue·report 등)는 재사용하면 같은 제목의 앞 문서를 덮으므로 항상 새 번호
    reuse_title = final_title if skill_id in EVIDENCE_SKILLS else None
    number = issue_num if issue_num else get_next_seq(skill_dir, today, title=reuse_title)

    path = build_output_path(output_base, skill_id, today, number, final_title)
    out = {
        "path": str(path),
        "summary": str(path),
        "mismatch": mismatch,
        "output_root": str(output_base),
    }
    if config_warning:
        out["config_warning"] = config_warning
    # 증거를 내는 스킬이면 폴더를 만들면서 제외 규칙을 함께 심는다.
    # 각 스킬이 알아서 하게 두면 빠뜨리는 스킬이 반드시 생긴다.
    if skill_id in EVIDENCE_SKILLS:
        out["gitignore"] = ensure_untracked(skill_dir, skill_id)
    return out
