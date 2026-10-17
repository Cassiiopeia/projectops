# -*- coding: utf-8 -*-
"""git 명령 실행: 저장소·브랜치 확인, 브랜치 생성, worktree 목록·정리·생성"""

import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

from git_worktree.console import IS_WINDOWS, print_error, print_info, print_step, print_success, print_warning


def run_git_command(args: list, check: bool = True) -> Tuple[bool, str, str]:
  """
  Git 명령어 실행

  Args:
      args: Git 명령어 인자 리스트 (예: ['branch', '--list'])
      check: 에러 발생 시 예외를 발생시킬지 여부

  Returns:
      Tuple[bool, str, str]: (성공 여부, stdout, stderr)
  """
  try:
    result = subprocess.run(
      ['git'] + args,
      capture_output=True,
      text=True,
      encoding='utf-8',
      check=check
    )
    return True, result.stdout.strip(), result.stderr.strip()
  except subprocess.CalledProcessError as e:
    return False, e.stdout.strip() if e.stdout else "", e.stderr.strip() if e.stderr else ""
  except Exception as e:
    return False, "", str(e)


def check_and_enable_longpaths() -> bool:
  """
  Windows에서 Git 긴 경로 지원 확인 및 활성화

  Returns:
      bool: 긴 경로 지원이 활성화되어 있으면 True
  """
  if not IS_WINDOWS:
    return True

  # 현재 설정 확인
  success, stdout, _ = run_git_command(['config', '--global', 'core.longpaths'], check=False)
  if success and stdout.strip().lower() == 'true':
    return True

  # 긴 경로 지원 활성화
  print_info("Windows 긴 경로 지원을 활성화합니다...")
  success, _, stderr = run_git_command(['config', '--global', 'core.longpaths', 'true'], check=False)
  if success:
    print_success("긴 경로 지원이 활성화되었습니다.")
    return True
  else:
    print_warning(f"긴 경로 지원 활성화 실패: {stderr}")
    print_warning("수동으로 실행하세요: git config --global core.longpaths true")
    return False


def is_git_repository() -> bool:
  """현재 디렉토리가 Git 저장소인지 확인"""
  success, _, _ = run_git_command(['rev-parse', '--git-dir'], check=False)
  return success


def get_git_root() -> Optional[Path]:
  """Git 저장소 루트 경로 반환"""
  success, stdout, _ = run_git_command(['rev-parse', '--show-toplevel'], check=False)
  if success and stdout:
    return Path(stdout)
  return None


def get_current_branch() -> Optional[str]:
  """현재 체크아웃된 브랜치명 반환"""
  success, stdout, _ = run_git_command(['branch', '--show-current'], check=False)
  if success and stdout:
    return stdout
  return None


def branch_exists(branch_name: str) -> bool:
  """
  로컬 브랜치 존재 여부 확인

  Args:
      branch_name: 확인할 브랜치명

  Returns:
      bool: 로컬 브랜치가 존재하면 True
  """
  success, stdout, _ = run_git_command(['branch', '--list', branch_name], check=False)
  if success and stdout:
    # 출력 형식: "  branch_name" 또는 "* branch_name"
    branches = [line.strip().lstrip('* ') for line in stdout.split('\n')]
    return branch_name in branches
  return False


def remote_branch_exists(branch_name: str, remote: str = 'origin') -> bool:
  """
  리모트에 브랜치가 존재하는지 확인

  Args:
      branch_name: 확인할 브랜치명
      remote: 리모트 이름 (기본: 'origin')

  Returns:
      bool: 리모트에 브랜치가 존재하면 True
  """
  success, stdout, _ = run_git_command(['branch', '-r', '--list', f'{remote}/{branch_name}'], check=False)
  if success and stdout:
    branches = [line.strip() for line in stdout.split('\n')]
    return f'{remote}/{branch_name}' in branches
  return False


def fetch_remote(remote: str = 'origin') -> bool:
  """
  리모트에서 최신 정보를 가져옵니다 (git fetch)

  Args:
      remote: 리모트 이름 (기본: 'origin')

  Returns:
      bool: 성공 여부
  """
  print_step("🔄", f"리모트({remote}) 최신 정보 가져오는 중...")
  success, _, stderr = run_git_command(['fetch', remote], check=False)
  if not success:
    print_warning(f"리모트 fetch 실패: {stderr}")
  return success


def create_branch(branch_name: str) -> bool:
  """
  새 브랜치 생성 (현재 브랜치에서 분기)

  Args:
      branch_name: 생성할 브랜치명

  Returns:
      bool: 성공 여부
  """
  success, _, stderr = run_git_command(['branch', branch_name], check=False)
  if not success:
    print_error(f"브랜치 생성 실패: {stderr}")
  return success


def create_branch_from_remote(branch_name: str, remote: str = 'origin') -> bool:
  """
  리모트 브랜치를 기반으로 로컬 tracking 브랜치 생성

  Args:
      branch_name: 생성할 브랜치명
      remote: 리모트 이름 (기본: 'origin')

  Returns:
      bool: 성공 여부
  """
  success, _, stderr = run_git_command(
    ['branch', '--track', branch_name, f'{remote}/{branch_name}'],
    check=False
  )
  if not success:
    print_error(f"리모트 브랜치 기반 로컬 브랜치 생성 실패: {stderr}")
  return success


def get_worktree_list() -> Dict[str, str]:
  """
  현재 등록된 worktree 목록 반환

  Returns:
      Dict[str, str]: {worktree_path: branch_name}
  """
  success, stdout, _ = run_git_command(['worktree', 'list', '--porcelain'], check=False)
  if not success:
    return {}

  worktrees = {}
  current_path = None

  for line in stdout.split('\n'):
    if line.startswith('worktree '):
      current_path = line.replace('worktree ', '')
    elif line.startswith('branch '):
      branch = line.replace('branch ', '').replace('refs/heads/', '')
      if current_path:
        worktrees[current_path] = branch
        current_path = None

  return worktrees


def prune_worktrees() -> bool:
  """
  유효하지 않은 worktree 정리 (git worktree prune)

  Returns:
      bool: 성공 여부
  """
  success, _, stderr = run_git_command(['worktree', 'prune'], check=False)
  if not success:
    print_warning(f"Worktree prune 실패: {stderr}")
  return success


def is_worktree_exists(worktree_path: Path) -> bool:
  """
  특정 경로에 worktree가 이미 존재하는지 확인

  Git worktree 목록과 실제 디렉토리 존재 여부를 모두 확인합니다.
  prunable 상태의 worktree는 자동으로 정리합니다.

  Args:
      worktree_path: 확인할 worktree 경로

  Returns:
      bool: worktree가 유효하게 존재하면 True
  """
  # 먼저 prunable worktree 정리
  prune_worktrees()

  worktrees = get_worktree_list()
  worktree_path_resolved = worktree_path.resolve()

  for path in worktrees.keys():
    if Path(path).resolve() == worktree_path_resolved:
      # Git 목록에 있으면 실제 디렉토리도 존재하는지 확인
      if Path(path).exists():
        return True
      else:
        # 디렉토리가 없으면 다시 prune 실행
        print_warning(f"Worktree 경로가 존재하지 않아 정리합니다: {path}")
        prune_worktrees()
        return False

  # 디렉토리만 존재하고 Git에 등록되지 않은 경우도 확인
  if worktree_path_resolved.exists():
    # .git 파일이 있는지 확인 (worktree의 특징)
    git_file = worktree_path_resolved / '.git'
    if git_file.exists():
      print_warning(f"디렉토리가 존재하지만 Git에 등록되지 않음: {worktree_path}")
      return True

  return False


def create_worktree(branch_name: str, worktree_path: Path) -> Dict:
  """
  Git worktree 생성

  Args:
      branch_name: 체크아웃할 브랜치명
      worktree_path: worktree를 생성할 경로

  Returns:
      Dict: {
          'success': bool,
          'path': str,
          'message': str,
          'is_existing': bool
      }
  """
  # 이미 존재하는지 확인
  if is_worktree_exists(worktree_path):
    return {
      'success': True,
      'path': str(worktree_path.resolve()),
      'message': 'Worktree가 이미 존재합니다.',
      'is_existing': True
    }

  # worktree 생성
  success, stdout, stderr = run_git_command(
    ['worktree', 'add', str(worktree_path), branch_name],
    check=False
  )

  if success:
    return {
      'success': True,
      'path': str(worktree_path.resolve()),
      'message': 'Worktree 생성 완료!',
      'is_existing': False
    }
  else:
    return {
      'success': False,
      'path': str(worktree_path.resolve()),
      'message': f'Worktree 생성 실패: {stderr}',
      'is_existing': False
    }
