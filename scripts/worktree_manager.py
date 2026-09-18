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

import os
import sys
import subprocess
import re
import platform
import io
import shutil
import glob
import fnmatch
from pathlib import Path
from typing import Dict, Optional, Tuple

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


# ===================================================================
# 상수 정의
# ===================================================================

VERSION = "1.1.0"

# Windows 환경 감지
IS_WINDOWS = platform.system() == 'Windows'

# 폴더명에서 제거할 특수문자 (파일시스템에서 안전하지 않은 문자)
SPECIAL_CHARS_PATTERN = r'[#/\\:*?"<>|]'

# Worktree 루트 폴더명 (동적으로 설정됨)
# 예: myapp → myapp-Worktree
WORKTREE_ROOT_NAME = None  # get_worktree_root()에서 동적으로 설정


# ===================================================================
# 유틸리티 함수
# ===================================================================

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
        pass

  # 기본: sys.argv에서 받기 (macOS/Linux 또는 Windows에서도 인자로 전달된 경우)
  if len(sys.argv) >= 2:
    return sys.argv[1].strip()

  return ''


def print_header():
  """헤더 출력"""
  print("━" * 60)
  print(f"🌿 Git Worktree Manager v{VERSION}")
  print("━" * 60)
  print()


def print_step(emoji: str, message: str):
  """단계별 메시지 출력"""
  print(f"{emoji} {message}")


def print_error(message: str):
  """에러 메시지 출력"""
  print(f"❌ 에러: {message}", file=sys.stderr)


def print_success(message: str):
  """성공 메시지 출력"""
  print(f"✅ {message}")


def print_info(message: str):
  """정보 메시지 출력"""
  print(f"ℹ️  {message}")


def print_warning(message: str):
  """경고 메시지 출력"""
  print(f"⚠️  {message}")


# ===================================================================
# Git 관련 함수
# ===================================================================

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


# ===================================================================
# 경로 관련 함수
# ===================================================================

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


# ===================================================================
# Gitignore 기반 로컬 파일 복사
# ===================================================================

# 복사 비권장 패턴 — 재생성 가능하거나 IDE/캐시/빌드 결과물
SKIP_PATTERNS = [
  'build/', 'target/', '.gradle', 'node_modules', 'Pods/', '.dart_tool',
  'Generated', 'generate', '.last_build_id', '.framework', '.flx', '.zip',
  'DerivedData', 'XCBuildData', '.class', '.pyc', '.log', '.symbols', '.map.json',
  '.pub-cache', '.pub/', 'migrate_working_dir', '.history', '.svn', '.swiftpm',
  'bin/', 'out/', 'dist/', 'nbproject', '.sts4-cache', '.springBeans',
  '.idea', '.vscode', '.DS_Store', '.flutter-plugins', 'flutter_export_environment.sh',
  '-Worktree/', 'venv/', '.gstack/', '.superpowers/', '__pycache__/',
  'tool/venv', 'tool/node_modules',
]

# 복사 권장 패턴 — 런타임/인증/플랫폼 설정
RECOMMEND_PATTERNS = [
  '.env', '.env.local', '.env.',
  'application-', 'application.',
  'key.properties', '.jks', '.keystore',
  'service-account', 'firebase-key',
  'google-services.json', 'GoogleService-Info.plist',
  'Secrets.xcconfig', 'secrets.xcconfig',
]


def should_skip(pattern: str) -> bool:
  """복사 비권장 패턴인지 확인"""
  p = pattern.lower()
  for skip in SKIP_PATTERNS:
    if skip.lower() in p:
      return True
  return False


def classify_file(rel_path: str) -> str:
  """파일 분류: recommend / skip"""
  name = Path(rel_path).name
  for rec in RECOMMEND_PATTERNS:
    if rec.lower() in name.lower() or rec.lower() in rel_path.lower():
      return 'recommend'
  return 'skip'


def parse_gitignore(git_root: Path):
  """
  .gitignore에서 단순 패턴 추출 (negation/주석/빈줄/복잡한 glob 제외)
  """
  gitignore = git_root / '.gitignore'
  if not gitignore.exists():
    return []

  patterns = []
  with open(gitignore, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
      line = line.strip()
      if not line or line.startswith('#') or line.startswith('!'):
        continue
      if '**' in line:
        continue
      patterns.append(line)
  return patterns


def find_local_files(git_root: Path, patterns: list) -> list:
  """
  패턴 목록에서 소스 루트에 실제 존재하는 파일 탐색 (1MB 이하)
  반환: [(절대경로, 소스루트 기준 상대경로)] 리스트
  """
  found = []
  seen = set()

  for pattern in patterns:
    # 단순 경로 (와일드카드 없음)
    if '*' not in pattern and '?' not in pattern:
      candidate = git_root / pattern
      if candidate.is_file() and candidate.stat().st_size < 1_048_576:
        rel = str(candidate.relative_to(git_root))
        if rel not in seen:
          seen.add(rel)
          found.append((candidate, rel))
    else:
      # 와일드카드 패턴 — find로 탐색
      for match in git_root.rglob(pattern.lstrip('/')):
        if not match.is_file():
          continue
        if match.stat().st_size >= 1_048_576:
          continue
        rel = str(match.relative_to(git_root))
        # 빌드/캐시 경로 제외
        skip_dirs = {'build', 'target', '.gradle', 'node_modules', 'Pods',
                     '.dart_tool', 'DerivedData', 'dist', 'out', 'bin'}
        parts = set(match.parts)
        if parts & skip_dirs:
          continue
        # 워크트리 경로 제외
        if '-Worktree' in str(match):
          continue
        if rel not in seen:
          seen.add(rel)
          found.append((match, rel))

  return found


def copy_local_files(git_root: Path, worktree_path: Path):
  """
  .gitignore 기반 로컬 파일을 worktree에 자동 복사하고 결과 출력
  """
  print()
  print("━" * 60)
  print("📋 로컬 설정 파일 복사")
  print("━" * 60)

  patterns = parse_gitignore(git_root)
  if not patterns:
    print_info(".gitignore 없음 — 복사 스킵")
    return

  candidates = find_local_files(git_root, patterns)

  copied = []
  skipped = []

  for abs_path, rel_path in candidates:
    # 비권장 패턴이면 스킵
    if should_skip(rel_path):
      skipped.append((rel_path, '빌드/캐시/IDE 파일'))
      continue

    # 이미 워크트리에 존재하면 스킵
    dest = worktree_path / rel_path
    if dest.exists():
      skipped.append((rel_path, '워크트리에 이미 존재'))
      continue

    classification = classify_file(rel_path)

    if classification == 'recommend':
      # 복사 실행
      try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(abs_path), str(dest))
        if dest.exists():
          copied.append((rel_path, '런타임/인증/플랫폼 설정 파일'))
        else:
          skipped.append((rel_path, '복사 후 파일 미확인'))
      except Exception as e:
        skipped.append((rel_path, f'복사 실패: {e}'))
    else:
      skipped.append((rel_path, '복사 권장 패턴 미해당'))

  # 결과 출력
  if copied:
    print()
    for rel, reason in copied:
      print(f"  ✅ copied  {rel}")
      print(f"     reason: {reason}")
  else:
    print_info("복사된 파일 없음")

  if skipped:
    print()
    print("  ⏭ 스킵된 파일:")
    for rel, reason in skipped:
      print(f"     - {rel}")
      print(f"       reason: {reason}")

  print()


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
      current_branch = get_current_branch()
      if current_branch:
        print_step("🔄", f"현재 브랜치({current_branch})에서 새 브랜치 생성 중...")
      else:
        print_step("🔄", "새 브랜치 생성 중...")

      if not create_branch(branch_name):
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
