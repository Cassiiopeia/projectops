# -*- coding: utf-8 -*-
"""Branch name input: Windows environment variable > file > stdin > argv, in that order"""

import os
import sys

from git_worktree.console import IS_WINDOWS, print_warning


def get_base_ref() -> str:
  """Ref to branch the new branch from: GIT_BASE_REF environment variable > `--base <ref>` argument. Empty string if neither (#944)"""
  from_env = os.environ.get('GIT_BASE_REF', '').strip()
  if from_env:
    return from_env
  args = sys.argv[1:]
  for position, arg in enumerate(args):
    if arg == '--base' and position + 1 < len(args):
      return args[position + 1].strip()
    if arg.startswith('--base='):
      return arg.split('=', 1)[1].strip()
  return ''


def get_branch_name() -> str:
  """
  Get the branch name safely (works around Windows encoding issues)

  Passing a Korean branch name from PowerShell to a Python script on Windows
  causes encoding issues, so reading from an environment variable or file is preferred.

  Returns:
      str: Branch name (may be empty)
  """
  # Check the environment variable first on every platform (macOS/Linux callers may also pass an empty argv, #944)
  if not IS_WINDOWS:
    branch_name = os.environ.get('GIT_BRANCH_NAME', '').strip()
    if branch_name:
      return branch_name

  if IS_WINDOWS:
    # Method 1: read from environment variable (simplest and safest)
    # Windows environment variables use the system default encoding, so try decoding as UTF-8
    branch_name_raw = os.environ.get('GIT_BRANCH_NAME', '')
    if branch_name_raw:
      try:
        # Environment variable already has the correct encoding
        branch_name = branch_name_raw.strip()
        # Check whether Korean text is garbled (try to recover if so)
        if '\xef\xbf\xbd' in branch_name.encode('utf-8', errors='replace').decode('utf-8', errors='replace'):
          # Garbled: try re-encoding with the system encoding and decoding as UTF-8
          import locale
          sys_encoding = locale.getpreferredencoding()
          branch_name = branch_name_raw.encode(sys_encoding, errors='replace').decode('utf-8', errors='replace').strip()
        else:
          branch_name = branch_name.strip()
        if branch_name:
          return branch_name
      except Exception:
        # Use the original value if conversion fails
        branch_name = branch_name_raw.strip()
        if branch_name:
          return branch_name

    # Method 2: read from a temp file (init-worktree creates it and passes the path)
    temp_file = os.environ.get('BRANCH_NAME_FILE', '')
    if temp_file and os.path.exists(temp_file):
      try:
        # Try several encodings: UTF-8, UTF-8 with BOM, system default encodings
        encodings = ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr']
        branch_name = None
        for encoding in encodings:
          try:
            with open(temp_file, 'r', encoding=encoding) as f:
              branch_name = f.read().strip()
              if branch_name and not any(ord(c) > 0xFFFF for c in branch_name if ord(c) > 0x7F):
                # Check that Korean text was read correctly (no garbled characters)
                break
          except (UnicodeDecodeError, UnicodeError):
            continue

        if branch_name:
          return branch_name
      except Exception as e:
        print_warning(f"Failed to read branch name file: {e}")

    # Method 3: try reading from stdin (piped input)
    if not sys.stdin.isatty():
      try:
        branch_name = sys.stdin.read().strip()
        if branch_name:
          return branch_name
      except Exception:
        pass  # If stdin cannot be read, fall back to argv below

  # Default: read from sys.argv (macOS/Linux, or Windows when passed as an argument)
  positional = [arg for arg in sys.argv[1:] if not arg.startswith('--')]
  if positional:
    return positional[0].strip()

  return ''
