# -*- coding: utf-8 -*-
"""Git command execution: repository/branch checks, branch creation, worktree list/prune/create"""

import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

from git_worktree.console import IS_WINDOWS, print_error, print_info, print_step, print_success, print_warning


def run_git_command(args: list, check: bool = True) -> Tuple[bool, str, str]:
  """
  Run a Git command

  Args:
      args: List of Git command arguments (e.g. ['branch', '--list'])
      check: Whether to raise an exception on error

  Returns:
      Tuple[bool, str, str]: (success, stdout, stderr)
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
  Check and enable Git long path support on Windows

  Returns:
      bool: True if long path support is enabled
  """
  if not IS_WINDOWS:
    return True

  # Check current setting
  success, stdout, _ = run_git_command(['config', '--global', 'core.longpaths'], check=False)
  if success and stdout.strip().lower() == 'true':
    return True

  # Enable long path support
  print_info("Enabling Windows long path support...")
  success, _, stderr = run_git_command(['config', '--global', 'core.longpaths', 'true'], check=False)
  if success:
    print_success("Long path support enabled.")
    return True
  else:
    print_warning(f"Failed to enable long path support: {stderr}")
    print_warning("Run manually: git config --global core.longpaths true")
    return False


def is_git_repository() -> bool:
  """Check whether the current directory is a Git repository"""
  success, _, _ = run_git_command(['rev-parse', '--git-dir'], check=False)
  return success


def get_git_root() -> Optional[Path]:
  """Return the Git repository root path"""
  success, stdout, _ = run_git_command(['rev-parse', '--show-toplevel'], check=False)
  if success and stdout:
    return Path(stdout)
  return None


def get_current_branch() -> Optional[str]:
  """Return the currently checked-out branch name"""
  success, stdout, _ = run_git_command(['branch', '--show-current'], check=False)
  if success and stdout:
    return stdout
  return None


def branch_exists(branch_name: str) -> bool:
  """
  Check whether a local branch exists

  Args:
      branch_name: Branch name to check

  Returns:
      bool: True if the local branch exists
  """
  success, stdout, _ = run_git_command(['branch', '--list', branch_name], check=False)
  if success and stdout:
    # Output format: "  branch_name" or "* branch_name"
    branches = [line.strip().lstrip('* ') for line in stdout.split('\n')]
    return branch_name in branches
  return False


def remote_branch_exists(branch_name: str, remote: str = 'origin') -> bool:
  """
  Check whether a branch exists on the remote

  Args:
      branch_name: Branch name to check
      remote: Remote name (default: 'origin')

  Returns:
      bool: True if the branch exists on the remote
  """
  success, stdout, _ = run_git_command(['branch', '-r', '--list', f'{remote}/{branch_name}'], check=False)
  if success and stdout:
    branches = [line.strip() for line in stdout.split('\n')]
    return f'{remote}/{branch_name}' in branches
  return False


def fetch_remote(remote: str = 'origin') -> bool:
  """
  Fetch the latest information from the remote (git fetch)

  Args:
      remote: Remote name (default: 'origin')

  Returns:
      bool: Whether it succeeded
  """
  print_step("🔄", f"Fetching latest from remote ({remote})...")
  success, _, stderr = run_git_command(['fetch', remote], check=False)
  if not success:
    print_warning(f"Remote fetch failed: {stderr}")
  return success


def create_branch(branch_name: str, base_ref: Optional[str] = None) -> bool:
  """
  Create a new branch (from base_ref, or the current branch if none). No upstream is set for base_ref (#944)

  Args:
      branch_name: Branch name to create
      base_ref: Ref to branch from (e.g. origin/develop)

  Returns:
      bool: Whether it succeeded
  """
  command = ['branch', '--no-track', branch_name, base_ref] if base_ref else ['branch', branch_name]
  success, _, stderr = run_git_command(command, check=False)
  if not success:
    print_error(f"Failed to create branch: {stderr}")
  return success


def create_branch_from_remote(branch_name: str, remote: str = 'origin') -> bool:
  """
  Create a local tracking branch from the remote branch

  Args:
      branch_name: Branch name to create
      remote: Remote name (default: 'origin')

  Returns:
      bool: Whether it succeeded
  """
  success, _, stderr = run_git_command(
    ['branch', '--track', branch_name, f'{remote}/{branch_name}'],
    check=False
  )
  if not success:
    print_error(f"Failed to create local branch from remote branch: {stderr}")
  return success


def get_worktree_list() -> Dict[str, str]:
  """
  Return the currently registered worktrees

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
  Clean up invalid worktrees (git worktree prune)

  Returns:
      bool: Whether it succeeded
  """
  success, _, stderr = run_git_command(['worktree', 'prune'], check=False)
  if not success:
    print_warning(f"Worktree prune failed: {stderr}")
  return success


def is_worktree_exists(worktree_path: Path) -> bool:
  """
  Check whether a worktree already exists at the given path

  Checks both the Git worktree list and whether the directory actually exists.
  Prunable worktrees are cleaned up automatically.

  Args:
      worktree_path: Worktree path to check

  Returns:
      bool: True if a valid worktree exists
  """
  # Clean up prunable worktrees first
  prune_worktrees()

  worktrees = get_worktree_list()
  worktree_path_resolved = worktree_path.resolve()

  for path in worktrees.keys():
    if Path(path).resolve() == worktree_path_resolved:
      # Listed in Git: check that the directory actually exists too
      if Path(path).exists():
        return True
      else:
        # Directory missing: prune again
        print_warning(f"Worktree path does not exist, pruning: {path}")
        prune_worktrees()
        return False

  # Also check for a directory that exists but is not registered in Git
  if worktree_path_resolved.exists():
    # Check for a .git file (a worktree marker)
    git_file = worktree_path_resolved / '.git'
    if git_file.exists():
      print_warning(f"Directory exists but is not registered in Git: {worktree_path}")
      return True

  return False


def create_worktree(branch_name: str, worktree_path: Path) -> Dict:
  """
  Create a Git worktree

  Args:
      branch_name: Branch name to check out
      worktree_path: Path to create the worktree at

  Returns:
      Dict: {
          'success': bool,
          'path': str,
          'message': str,
          'is_existing': bool
      }
  """
  # Check whether it already exists
  if is_worktree_exists(worktree_path):
    return {
      'success': True,
      'path': str(worktree_path.resolve()),
      'message': 'Worktree already exists.',
      'is_existing': True
    }

  # Create the worktree
  success, stdout, stderr = run_git_command(
    ['worktree', 'add', str(worktree_path), branch_name],
    check=False
  )

  if success:
    return {
      'success': True,
      'path': str(worktree_path.resolve()),
      'message': 'Worktree created!',
      'is_existing': False
    }
  else:
    return {
      'success': False,
      'path': str(worktree_path.resolve()),
      'message': f'Failed to create worktree: {stderr}',
      'is_existing': False
    }
