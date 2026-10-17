# -*- coding: utf-8 -*-
"""worktree 경로 계산: 브랜치명 > 폴더명, {프로젝트명}-Worktree 루트, 디렉토리 생성"""

import re
from pathlib import Path

from git_worktree.console import print_error
from git_worktree.git_commands import get_git_root

# 폴더명에서 제거할 특수문자 (파일시스템에서 안전하지 않은 문자)
SPECIAL_CHARS_PATTERN = r'[#/\\:*?"<>|]'

# Worktree 루트 폴더명 (동적으로 설정됨)
# 예: myapp → myapp-Worktree
WORKTREE_ROOT_NAME = None  # get_worktree_root()에서 동적으로 설정


def normalize_branch_name(branch_name: str) -> str:
  """
  브랜치명을 폴더명으로 안전하게 변환

  특수문자 (#, /, \\, :, *, ?, ", <, >, |)를 _ 로 변환하고,
  연속된 _를 하나로 통합하며, 앞뒤 _를 제거합니다.

  Args:
      branch_name: 원본 브랜치명

  Returns:
      str: 정규화된 폴더명

  Example:
      >>> normalize_branch_name("20260120_#163_Github_Projects")
      "20260120_163_Github_Projects"
  """
  # 특수문자를 _ 로 변환
  normalized = re.sub(SPECIAL_CHARS_PATTERN, '_', branch_name)

  # 연속된 _를 하나로 통합
  normalized = re.sub(r'_+', '_', normalized)

  # 앞뒤 _를 제거
  normalized = normalized.strip('_')

  return normalized


def get_worktree_root() -> Path:
  """
  Worktree 루트 경로 계산

  현재 Git 저장소의 부모 디렉토리에 {프로젝트명}-Worktree 폴더 생성

  Returns:
      Path: Worktree 루트 경로

  Example:
      현재: /Users/.../project/myapp
      반환: /Users/.../project/myapp-Worktree
  """
  git_root = get_git_root()
  if not git_root:
    raise RuntimeError("Git 저장소 루트를 찾을 수 없습니다.")

  # 현재 Git 저장소의 이름 추출 (예: myapp)
  project_name = git_root.name

  # 부모 디렉토리에 {프로젝트명}-Worktree 폴더 생성
  worktree_root_name = f"{project_name}-Worktree"
  worktree_root = git_root.parent / worktree_root_name

  return worktree_root


def get_worktree_path(branch_name: str) -> Path:
  """
  특정 브랜치의 worktree 전체 경로 반환

  Args:
      branch_name: 브랜치명 (정규화 전)

  Returns:
      Path: Worktree 경로

  Example:
      >>> get_worktree_path("20260120_#163_Github_Projects")
      Path("/Users/.../project/myapp-Worktree/20260120_163_Github_Projects")
  """
  worktree_root = get_worktree_root()
  folder_name = normalize_branch_name(branch_name)
  return worktree_root / folder_name


def ensure_directory(path: Path) -> bool:
  """
  디렉토리가 존재하지 않으면 생성

  Args:
      path: 생성할 디렉토리 경로

  Returns:
      bool: 성공 여부
  """
  try:
    path.mkdir(parents=True, exist_ok=True)
    return True
  except Exception as e:
    print_error(f"디렉토리 생성 실패: {e}")
    return False
