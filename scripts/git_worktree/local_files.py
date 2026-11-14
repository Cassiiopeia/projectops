# -*- coding: utf-8 -*-
"""Local file copy based on .gitignore: extract patterns > find files > classify recommended/not recommended > copy and print results"""

import shutil
from pathlib import Path

from git_worktree.console import print_info

# Patterns not recommended for copying — regenerable, or IDE/cache/build output
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

# Patterns recommended for copying — runtime/auth/platform settings
RECOMMEND_PATTERNS = [
  '.env', '.env.local', '.env.',
  'application-', 'application.',
  'key.properties', '.jks', '.keystore',
  'service-account', 'firebase-key',
  'google-services.json', 'GoogleService-Info.plist',
  'Secrets.xcconfig', 'secrets.xcconfig',
]


def should_skip(pattern: str) -> bool:
  """Check whether the pattern is not recommended for copying"""
  p = pattern.lower()
  for skip in SKIP_PATTERNS:
    if skip.lower() in p:
      return True
  return False


def classify_file(rel_path: str) -> str:
  """Classify a file: recommend / skip"""
  name = Path(rel_path).name
  for rec in RECOMMEND_PATTERNS:
    if rec.lower() in name.lower() or rec.lower() in rel_path.lower():
      return 'recommend'
  return 'skip'


def parse_gitignore(git_root: Path):
  """
  Extract simple patterns from .gitignore (excluding negations/comments/blank lines/complex globs)
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
  Find files from the pattern list that actually exist in the source root (under 1MB)
  Returns: list of [(absolute path, path relative to source root)]
  """
  found = []
  seen = set()

  for pattern in patterns:
    # Plain path (no wildcard)
    if '*' not in pattern and '?' not in pattern:
      candidate = git_root / pattern
      if candidate.is_file() and candidate.stat().st_size < 1_048_576:
        rel = str(candidate.relative_to(git_root))
        if rel not in seen:
          seen.add(rel)
          found.append((candidate, rel))
    else:
      # Wildcard pattern — search with rglob
      for match in git_root.rglob(pattern.lstrip('/')):
        if not match.is_file():
          continue
        if match.stat().st_size >= 1_048_576:
          continue
        rel = str(match.relative_to(git_root))
        # Exclude build/cache paths
        skip_dirs = {'build', 'target', '.gradle', 'node_modules', 'Pods',
                     '.dart_tool', 'DerivedData', 'dist', 'out', 'bin'}
        parts = set(match.parts)
        if parts & skip_dirs:
          continue
        # Exclude worktree paths
        if '-Worktree' in str(match):
          continue
        if rel not in seen:
          seen.add(rel)
          found.append((match, rel))

  return found


def copy_local_files(git_root: Path, worktree_path: Path):
  """
  Automatically copy .gitignore-based local files into the worktree and print the results
  """
  print()
  print("━" * 60)
  print("📋 Copying local config files")
  print("━" * 60)

  patterns = parse_gitignore(git_root)
  if not patterns:
    print_info("No .gitignore — skipping copy")
    return

  candidates = find_local_files(git_root, patterns)

  copied = []
  skipped = []

  for abs_path, rel_path in candidates:
    # Skip patterns not recommended for copying
    if should_skip(rel_path):
      skipped.append((rel_path, 'build/cache/IDE file'))
      continue

    # Skip if it already exists in the worktree
    dest = worktree_path / rel_path
    if dest.exists():
      skipped.append((rel_path, 'already exists in worktree'))
      continue

    classification = classify_file(rel_path)

    if classification == 'recommend':
      # Copy
      try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(abs_path), str(dest))
        if dest.exists():
          copied.append((rel_path, 'runtime/auth/platform config file'))
        else:
          skipped.append((rel_path, 'file not found after copy'))
      except Exception as e:
        skipped.append((rel_path, f'copy failed: {e}'))
    else:
      skipped.append((rel_path, 'does not match a recommended copy pattern'))

  # Print results
  if copied:
    print()
    for rel, reason in copied:
      print(f"  ✅ copied  {rel}")
      print(f"     reason: {reason}")
  else:
    print_info("No files copied")

  if skipped:
    print()
    print("  ⏭ Skipped files:")
    for rel, reason in skipped:
      print(f"     - {rel}")
      print(f"       reason: {reason}")

  print()
