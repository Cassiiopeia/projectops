# -*- coding: utf-8 -*-
"""
Git Worktree Manager v1.2.0

A script to automatically create and manage Git worktrees.
If a branch does not exist, it checks the remote (origin) and creates it automatically, safely handling special characters in branch names.
After creating the worktree, it automatically copies local configuration files based on .gitignore.

Usage:
    macOS/Linux:
        python worktree_manager.py <branch_name>

    Windows (recommended environment variable method):
        $env:GIT_BRANCH_NAME = "branch_name"
        $env:PYTHONIOENCODING = "utf-8"
        python -X utf8 worktree_manager.py

Example:
    python worktree_manager.py "20260120_#163_Github_Projects_Need_for_Template_Development"

Author: Cursor AI Assistant
Version: 1.2.0
"""

import io
import platform
import sys
from pathlib import Path

# Fix Windows encoding issues - wrap stdout/stderr in UTF-8
if platform.system() == 'Windows':
    try:
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass  # Ignore wrapping failures

# Implementation is based on the git_worktree package in the same folder (finds based on this file's location)
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Re-expose names used by external callers
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
# Main Workflow
# ===================================================================

def main() -> int:
    """
    Main workflow

    Returns:
        int: Exit code (0: success, 1: failure)
    """
    print_header()

    # 1. Get branch name (Windows environment support)
    branch_name = get_branch_name()

    if not branch_name:
        print_error("No branch name provided.")
        print()
        print("Usage:")
        if IS_WINDOWS:
            print("  Windows environment:")
            print("    Method 1: Use environment variable")
            print(f'      $env:GIT_BRANCH_NAME = "branch_name"')
            print(f"      python {sys.argv[0]}")
            print()
            print("    Method 2: Use file")
            print(f'      $env:BRANCH_NAME_FILE = "branch_name.txt"')
            print(f"      python {sys.argv[0]}")
            print()
            print("    Method 3: Pass as argument (may cause character corruption)")
            print(f'      python {sys.argv[0]} "branch_name"')
        else:
            print(f"  python {sys.argv[0]} <branch_name>")
        print()
        print("Example:")
        print(f'  python {sys.argv[0]} "20260120_#163_Github_Projects_Need_for_Template_Development"')
        return 1

    print_step("📋", f"Input branch: {branch_name}")

    # 2. Check if it's a Git repository
    if not is_git_repository():
        print_error("The current directory is not a Git repository.")
        return 1

    # 2-1. Check and enable long path support on Windows
    if IS_WINDOWS:
        check_and_enable_longpaths()
        print()

    # 3. Normalize branch name
    folder_name = normalize_branch_name(branch_name)
    print_step("📁", f"Folder name: {folder_name}")
    print()

    # 4. Check if branch exists (local → remote order)
    print_step("🔍", "Checking branch...")

    if branch_exists(branch_name):
        print_success("Local branch already exists.")
    else:
        print_warning("Local branch does not exist.")

        # Fetch latest information from remote
        fetch_remote()

        if remote_branch_exists(branch_name):
            # If the branch exists on remote, create it as a tracking branch
            print_step("🌐", f"Fetching branch from remote (origin/{branch_name})...")

            if not create_branch_from_remote(branch_name):
                print_error("Failed to create local branch from remote branch.")
                return 1

            print_success(f"Successfully created local branch based on remote branch (origin/{branch_name})!")
        else:
            # If it doesn't exist on remote, create a new one from the current branch
            base_ref = get_base_ref()
            current_branch = get_current_branch()
            if base_ref:
                print_step("🔄", f"Creating new branch from {base_ref}...")
            elif current_branch:
                print_step("🔄", f"Creating new branch from current branch ({current_branch})...")
            else:
                print_step("🔄", "Creating new branch...")

            if not create_branch(branch_name, base_ref):
                print_error("Failed to create branch.")
                return 1

            print_success("New branch created successfully!")

    print()

    # 5. Calculate worktree path
    try:
        worktree_path = get_worktree_path(branch_name)
    except RuntimeError as e:
        print_error(str(e))
        return 1

    print_step("📂", f"Worktree path: {worktree_path}")
    print()

    # 6. Check if worktree exists
    print_step("🔍", "Checking worktree...")

    if is_worktree_exists(worktree_path):
        print_info("Worktree already exists.")
        print()
        print_step("📍", f"Path: {worktree_path.resolve()}")
        return 0

    # 7. Create worktree root directory
    worktree_root = get_worktree_root()
    if not ensure_directory(worktree_root):
        return 1

    # 8. Create worktree
    print_step("🔄", "Creating worktree...")

    result = create_worktree(branch_name, worktree_path)

    if result['success']:
        if result['is_existing']:
            print_info(result['message'])
        else:
            print_success(result['message'])

        print()
        print_step("📍", f"Path: {result['path']}")

        # Automatically copy local files based on gitignore if worktree creation is successful
        git_root = get_git_root()
        if git_root:
            copy_local_files(git_root, worktree_path)

        return 0
    else:
        print_error(result['message'])
        return 1


# ===================================================================
# Entry Point
# ===================================================================

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print()
        print_warning("Interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print()
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)