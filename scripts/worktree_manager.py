# -*- coding: utf-8 -*-
"""
Git Worktree Manager v1.2.0

Git worktree를 자동으로 생성하고 관리하는 스크립트입니다.
브랜치가 없으면 리모트(origin) 확인 후 자동으로 생성하고, 브랜치명의 특수문자를 안전하게 처리합니다.
worktree 생성 후 .gitignore 기반 로컬 설정 파일을 자동으로 복사합니다.

사용법:
    macOS/Linux:
        python worktree_manager.py <branch_name>

    Windows (환경 변수 방식, 권장):
        $env:GIT_BRANCH_NAME = "브랜치명"
        $env:PYTHONIOENCODING = "utf-8"
        python -X utf8 worktree_manager.py

예시:
    python worktree_manager.py "20260120_#163_Github_Projects_에_대한_템플릿_개발_필요"

Author: Cursor AI Assistant
Version: 1.2.0
"""

import io
import platform
import sys
from pathlib import Path

# Windows 인코딩 문제 해결 - stdout/stderr를 UTF-8로 래핑
if platform.system() == 'Windows':
  try:
    # stdout/stderr가 버퍼를 가지고 있는 경우에만 래핑
    if hasattr(sys.stdout, 'buffer'):
      sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
      sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
  except Exception:
    pass  # 래핑 실패 시 무시

# 구현은 같은 폴더의 git_worktree 패키지 (설치 위치와 무관하게 이 파일 기준으로 찾음)
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
  sys.path.insert(0, _SCRIPTS_DIR)

# 외부 호출부가 쓰는 이름 재노출
from git_worktree.console import (  # noqa: E402,F401
  VERSION, IS_WINDOWS, print_header, print_step, print_error, print_success, print_info, print_warning,
)
from git_worktree.branch_input import get_base_ref, get_branch_name  # noqa: E402,F401
from git_worktree.git_commands import (  # noqa: E402,F401
  run_git_command, check_and_enable_longpaths, is_git_repository, get_git_root, get_current_branch,
  branch_exists, remote_branch_exists, fetch_remote, create_branch, create_branch_from_remote,
  get_worktree_list, prune_worktrees, is_worktree_exists, create_worktree,
)
from git_worktree.paths import (  # noqa: E402,F401
  SPECIAL_CHARS_PATTERN, WORKTREE_ROOT_NAME, normalize_branch_name, get_worktree_root, get_worktree_path,
  ensure_directory,
)
from git_worktree.local_files import (  # noqa: E402,F401
  SKIP_PATTERNS, RECOMMEND_PATTERNS, should_skip, classify_file, parse_gitignore, find_local_files,
  copy_local_files,
)


# ===================================================================
# 메인 워크플로우
# ===================================================================

def main() -> int:
  """
  메인 워크플로우

  Returns:
      int: Exit code (0: 성공, 1: 실패)
  """
  print_header()

  # 1. 브랜치명 받기 (Windows 환경 대응)
  branch_name = get_branch_name()

  if not branch_name:
    print_error("브랜치명이 제공되지 않았습니다.")
    print()
    print("사용법:")
    if IS_WINDOWS:
      print("  Windows 환경:")
      print("    방법 1: 환경 변수 사용")
      print(f'      $env:GIT_BRANCH_NAME = "브랜치명"')
      print(f"      python {sys.argv[0]}")
      print()
      print("    방법 2: 파일 사용")
      print(f'      $env:BRANCH_NAME_FILE = "branch_name.txt"')
      print(f"      python {sys.argv[0]}")
      print()
      print("    방법 3: 인자로 전달 (한글 깨짐 가능)")
      print(f'      python {sys.argv[0]} "브랜치명"')
    else:
      print(f"  python {sys.argv[0]} <branch_name>")
    print()
    print("예시:")
    print(f'  python {sys.argv[0]} "20260120_#163_Github_Projects_에_대한_템플릿_개발_필요"')
    return 1

  print_step("📋", f"입력된 브랜치: {branch_name}")

  # 2. Git 저장소 확인
  if not is_git_repository():
    print_error("현재 디렉토리가 Git 저장소가 아닙니다.")
    return 1

  # 2-1. Windows 긴 경로 지원 확인 및 활성화
  if IS_WINDOWS:
    check_and_enable_longpaths()
    print()

  # 3. 브랜치명 정규화
  folder_name = normalize_branch_name(branch_name)
  print_step("📁", f"폴더명: {folder_name}")
  print()

  # 4. 브랜치 존재 확인 (로컬 → 리모트 순서)
  print_step("🔍", "브랜치 확인 중...")

  if branch_exists(branch_name):
    print_success("로컬 브랜치가 이미 존재합니다.")
  else:
    print_warning("로컬 브랜치가 존재하지 않습니다.")

    # 리모트에서 최신 정보 가져오기
    fetch_remote()

    if remote_branch_exists(branch_name):
      # 리모트에 브랜치가 있으면 tracking 브랜치로 생성
      print_step("🌐", f"리모트(origin/{branch_name})에서 브랜치를 가져옵니다...")

      if not create_branch_from_remote(branch_name):
        print_error("리모트 브랜치 기반 로컬 브랜치 생성에 실패했습니다.")
        return 1

      print_success(f"리모트 브랜치(origin/{branch_name})를 기반으로 로컬 브랜치 생성 완료!")
    else:
      # 리모트에도 없으면 현재 브랜치에서 새로 생성
      base_ref = get_base_ref()
      current_branch = get_current_branch()
      if base_ref:
        print_step("🔄", f"{base_ref} 에서 새 브랜치 생성 중...")
      elif current_branch:
        print_step("🔄", f"현재 브랜치({current_branch})에서 새 브랜치 생성 중...")
      else:
        print_step("🔄", "새 브랜치 생성 중...")

      if not create_branch(branch_name, base_ref):
        print_error("브랜치 생성에 실패했습니다.")
        return 1

      print_success("새 브랜치 생성 완료!")

  print()

  # 5. Worktree 경로 계산
  try:
    worktree_path = get_worktree_path(branch_name)
  except RuntimeError as e:
    print_error(str(e))
    return 1

  print_step("📂", f"Worktree 경로: {worktree_path}")
  print()

  # 6. Worktree 존재 확인
  print_step("🔍", "Worktree 확인 중...")

  if is_worktree_exists(worktree_path):
    print_info("Worktree가 이미 존재합니다.")
    print()
    print_step("📍", f"경로: {worktree_path.resolve()}")
    return 0

  # 7. Worktree 루트 디렉토리 생성
  worktree_root = get_worktree_root()
  if not ensure_directory(worktree_root):
    return 1

  # 8. Worktree 생성
  print_step("🔄", "Worktree 생성 중...")

  result = create_worktree(branch_name, worktree_path)

  if result['success']:
    if result['is_existing']:
      print_info(result['message'])
    else:
      print_success(result['message'])

    print()
    print_step("📍", f"경로: {result['path']}")

    # worktree 생성 성공 시 gitignore 기반 로컬 파일 자동 복사
    git_root = get_git_root()
    if git_root:
      copy_local_files(git_root, worktree_path)

    return 0
  else:
    print_error(result['message'])
    return 1


# ===================================================================
# 엔트리 포인트
# ===================================================================

if __name__ == "__main__":
  try:
    exit_code = main()
    sys.exit(exit_code)
  except KeyboardInterrupt:
    print()
    print_warning("사용자에 의해 중단되었습니다.")
    sys.exit(130)
  except Exception as e:
    print()
    print_error(f"예상치 못한 오류가 발생했습니다: {e}")
    sys.exit(1)
