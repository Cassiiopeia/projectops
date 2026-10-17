# -*- coding: utf-8 -*-
"""Worktree Manager 콘솔 출력: 버전, OS 판정, 단계·성공·경고·에러 메시지"""

import platform
import sys

VERSION = "1.1.0"

# Windows 환경 감지
IS_WINDOWS = platform.system() == 'Windows'


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
