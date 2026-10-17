# -*- coding: utf-8 -*-
"""브랜치명 입력: Windows 환경 변수 > 파일 > stdin > argv 순서"""

import os
import sys

from git_worktree.console import IS_WINDOWS, print_warning


def get_branch_name() -> str:
  """
  브랜치명을 안전하게 받기 (Windows 인코딩 문제 해결)

  Windows 환경에서 PowerShell → Python 스크립트로 한글 브랜치명을 전달할 때
  인코딩 문제가 발생하므로, 환경 변수나 파일에서 읽는 방식을 우선 사용합니다.

  Returns:
      str: 브랜치명 (비어있을 수 있음)
  """
  if IS_WINDOWS:
    # 방법 1: 환경 변수에서 읽기 (가장 간단하고 안전)
    # Windows에서 환경 변수는 시스템 기본 인코딩을 사용하므로 UTF-8로 디코딩 시도
    branch_name_raw = os.environ.get('GIT_BRANCH_NAME', '')
    if branch_name_raw:
      try:
        # 환경 변수가 이미 올바른 인코딩인 경우
        branch_name = branch_name_raw.strip()
        # 한글이 깨져있는지 확인 (깨진 경우 복구 시도)
        if '\xef\xbf\xbd' in branch_name.encode('utf-8', errors='replace').decode('utf-8', errors='replace'):
          # 깨진 경우, 시스템 인코딩으로 디코딩 후 UTF-8로 재인코딩 시도
          import locale
          sys_encoding = locale.getpreferredencoding()
          branch_name = branch_name_raw.encode(sys_encoding, errors='replace').decode('utf-8', errors='replace').strip()
        else:
          branch_name = branch_name.strip()
        if branch_name:
          return branch_name
      except Exception:
        # 인코딩 변환 실패 시 원본 사용
        branch_name = branch_name_raw.strip()
        if branch_name:
          return branch_name

    # 방법 2: 임시 파일에서 읽기 (init-worktree에서 파일 생성 후 전달)
    temp_file = os.environ.get('BRANCH_NAME_FILE', '')
    if temp_file and os.path.exists(temp_file):
      try:
        # 여러 인코딩 시도: UTF-8, UTF-8 with BOM, 시스템 기본 인코딩
        encodings = ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr']
        branch_name = None
        for encoding in encodings:
          try:
            with open(temp_file, 'r', encoding=encoding) as f:
              branch_name = f.read().strip()
              if branch_name and not any(ord(c) > 0xFFFF for c in branch_name if ord(c) > 0x7F):
                # 한글이 제대로 읽혔는지 확인 (깨진 문자가 없는지)
                break
          except (UnicodeDecodeError, UnicodeError):
            continue

        if branch_name:
          return branch_name
      except Exception as e:
        print_warning(f"브랜치명 파일 읽기 실패: {e}")

    # 방법 3: stdin에서 읽기 시도 (파이프 입력인 경우)
    if not sys.stdin.isatty():
      try:
        branch_name = sys.stdin.read().strip()
        if branch_name:
          return branch_name
      except Exception:
        pass  # stdin 을 못 읽으면 아래 argv 로 받는다

  # 기본: sys.argv에서 받기 (macOS/Linux 또는 Windows에서도 인자로 전달된 경우)
  if len(sys.argv) >= 2:
    return sys.argv[1].strip()

  return ''
