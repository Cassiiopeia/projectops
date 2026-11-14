# -*- coding: utf-8 -*-
"""Worktree path calculation: branch name > folder name, {project_name}-Worktree root, directory creation"""

import re
from pathlib import Path

from git_worktree.console import print_error
from git_worktree.git_commands import get_git_root

# Special characters to remove from folder names (unsafe on file systems)
SPECIAL_CHARS_PATTERN = r'[#/\\:*?"<>|]'

# Worktree root folder name (set dynamically)
# e.g. myapp → myapp-Worktree
WORKTREE_ROOT_NAME = None  # Set dynamically in get_worktree_root()


def normalize_branch_name(branch_name: str) -> str:
  """
  Safely convert a branch name to a folder name

  Replaces special characters (#, /, \\, :, *, ?, ", <, >, |) with _,
  collapses consecutive _ into one, and strips leading/trailing _.

  Args:
      branch_name: Original branch name

  Returns:
      str: Normalized folder name

  Example:
      >>> normalize_branch_name("20260120_#163_Github_Projects")
      "20260120_163_Github_Projects"
  """
  # Replace special characters with _
  normalized = re.sub(SPECIAL_CHARS_PATTERN, '_', branch_name)

  # Collapse consecutive _ into one
  normalized = re.sub(r'_+', '_', normalized)

  # Strip leading/trailing _
  normalized = normalized.strip('_')

  return normalized


def get_worktree_root() -> Path:
  """
  Calculate the worktree root path

  A {project_name}-Worktree folder in the parent directory of the current Git repository

  Returns:
      Path: Worktree root path

  Example:
      Current: /Users/.../project/myapp
      Returns: /Users/.../project/myapp-Worktree
  """
  git_root = get_git_root()
  if not git_root:
    raise RuntimeError("Cannot find the Git repository root.")

  # Get the current Git repository name (e.g. myapp)
  project_name = git_root.name

  # {project_name}-Worktree folder in the parent directory
  worktree_root_name = f"{project_name}-Worktree"
  worktree_root = git_root.parent / worktree_root_name

  return worktree_root


def get_worktree_path(branch_name: str) -> Path:
  """
  Return the full worktree path for a branch

  Args:
      branch_name: Branch name (before normalization)

  Returns:
      Path: Worktree path

  Example:
      >>> get_worktree_path("20260120_#163_Github_Projects")
      Path("/Users/.../project/myapp-Worktree/20260120_163_Github_Projects")
  """
  worktree_root = get_worktree_root()
  folder_name = normalize_branch_name(branch_name)
  return worktree_root / folder_name


def ensure_directory(path: Path) -> bool:
  """
  Create the directory if it does not exist

  Args:
      path: Directory path to create

  Returns:
      bool: Whether it succeeded
  """
  try:
    path.mkdir(parents=True, exist_ok=True)
    return True
  except Exception as e:
    print_error(f"Failed to create directory: {e}")
    return False
