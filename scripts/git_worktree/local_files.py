# -*- coding: utf-8 -*-
""".gitignore 기반 로컬 파일 복사: 패턴 추출 > 파일 탐색 > 권장·비권장 분류 > 복사·결과 출력"""

import shutil
from pathlib import Path

from git_worktree.console import print_info

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
