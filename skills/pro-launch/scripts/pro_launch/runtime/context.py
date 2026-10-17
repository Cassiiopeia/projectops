"""실행 한 번의 상태 — 프로젝트 루트 해석과 명령 사이에 넘기는 표시들."""
from __future__ import annotations

import os
from pathlib import Path

from common.state import base_dir, in_skill_path, migrate_launch, repo_unknown, state_dir

from pro_launch.runtime.recent_roots import is_git_work_tree, last_used_root, remember_root


# 이 프로세스에서 이미 옮겼는지. 한 번만 본다.
MIGRATION: dict = {}


def state_home(root: Path) -> Path:
    """launch 상태 폴더. 처음 부를 때 옛 agent-test 폴더의 launch 몫을 옮긴다."""
    key = str(root)
    if key not in MIGRATION:
        MIGRATION[key] = migrate_launch(root)
    return state_dir("launch", root)


# ── 레포를 알 수 없을 때 (#836) ──────────────────────────────────────────
#
# 스킬·플러그인 캐시 폴더에서 불렸고 git 원격도 없으면 어느 프로젝트인지 모른다. 이때 상태는
# 이 컴퓨터 공용 자리(_machine)에 쓰고(state.state_dir 이 정한다), 응답으로 --root 를 요구한다.
ROOT_CTX: dict = {}


# ── 적어 둔 접속 방법의 성적 (#836) ──────────────────────────────────────
#
# logs·db·http 가 access 기록으로 실행되면 결과를 도구가 직접 남긴다(기억 원칙 2).
# 미설치·환경변수 누락처럼 환경 탓인 실패는 방법의 실패가 아니므로 세지 않는다.
ACCESS_CTX: dict = {}


# ── 기억을 응답에 싣는다 (#833) ──────────────────────────────────────────
#
# 읽기를 agent 의 recall 호출에 맡겼더니 한 번도 다시 읽히지 않았다(실측: 14건 전부 ok=1).
# 그래서 영역(ios·android·web·server) 명령의 응답에 기억을 직접 싣는다 — 하네스와 무관하게 보인다.
# 명령이 영역을 정하면 MEMORY_CTX 에 적고, out() 이 마지막에 읽는다.
MEMORY_CTX: dict = {}


# ── 출력 모양 (#898) ──────────────────────────────────────────────────────
#
# 결과를 head·cut·python 으로 잘라 읽다가 next·memory·known_fix 가 버려졌다(실측 636+275회).
# 전역 --brief · --fields 를 cli.main 이 여기 적고, out() 이 마지막에 읽어 줄인다.
# is_brief: 핵심 키만 / field_names: 남길 최상위 키 (None 이면 전부)
OUTPUT_CTX: dict = {}


# ── 입력 표시 (#886) ──────────────────────────────────────────────────────
#
# empty_values: 값이 빈 문자열로 넘어온 옵션. 실패 응답에 싣는다 — 원인이 $VAR 미설정인 경우가 많다
INPUT_CTX: dict = {}


def project_root(args) -> Path:
    """작업 대상 프로젝트 루트: --root > $PROJECT_ROOT > 작업 폴더(git 이면) > 최근에 쓴 루트 > 작업 폴더 (#885).

    agent 셸은 호출마다 작업 폴더가 초기화돼, 레포 밖에서 불리면 git_not_found·browser_not_open 이 났다.
    agent 가 스크립트 폴더로 `cd` 한 뒤 `--root .` 으로 부르면 플러그인 캐시가 레포로 잡혀 기억이
    엉뚱한 곳(~/.projectops/launch/scripts/)에 쌓였다(#833 실측) — 그때도 $PROJECT_ROOT 를 쓴다.
    """
    raw = getattr(args, "root", ".") or "."
    cache_key = (raw, os.getcwd(), os.environ.get("PROJECT_ROOT"), str(base_dir()))
    if cache_key not in _RESOLVED_ROOTS:
        _RESOLVED_ROOTS[cache_key] = _resolve_root(raw)
    root, marks = _RESOLVED_ROOTS[cache_key]
    ROOT_CTX.update(marks, resolved=str(root))
    return root


# (--root 값, 작업 폴더, $PROJECT_ROOT) > (루트, ROOT_CTX 표시). 한 명령이 project_root 를 여러 번 불러도 git 을 한 번만 본다
_RESOLVED_ROOTS: dict = {}


def _resolve_root(raw: str) -> tuple[Path, dict]:
    env_root = os.environ.get("PROJECT_ROOT")
    candidate = Path(raw).expanduser().resolve()
    if raw != ".":
        if repo_unknown(candidate):
            if env_root:
                return _remembered(Path(env_root).expanduser().resolve()), {}
            # 상태는 state_dir 이 _machine 으로 돌린다. 응답에서 --root 를 요구하도록 표시만 한다
            return candidate, {"unknown": True, "path": str(candidate)}
        return _remembered(candidate), {}
    if env_root:
        return _remembered(Path(env_root).expanduser().resolve()), {}
    if is_git_work_tree(candidate) and not repo_unknown(candidate):
        return _remembered(candidate), {}
    last = last_used_root()
    if last is not None:
        return last, {"source": "last_used", "path": str(last), "cwd": str(candidate)}
    if repo_unknown(candidate):
        return candidate, {"unknown": True, "path": str(candidate)}
    # git 레포가 아닌 폴더 — 옛 동작대로 그 폴더를 쓰되, 실패하면 후보와 다시 부를 명령을 싣는다
    return candidate, {"not_repo": True, "path": str(candidate)}


def _remembered(root: Path) -> Path:
    remember_root(root)
    return root


# scripts/ 폴더 — 이 파일은 scripts/pro_launch/runtime/ 아래에 있다
SCRIPTS_DIR = Path(__file__).resolve().parents[2]


def is_skill_dir(r: Path) -> bool:
    """r 이 스킬·플러그인 폴더(이 스킬 자신 포함) 안인가 — 사용자 프로젝트가 아닐 수 있다."""
    return r in (SCRIPTS_DIR, SCRIPTS_DIR.parent) or in_skill_path(r)
