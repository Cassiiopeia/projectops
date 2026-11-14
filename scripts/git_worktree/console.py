# -*- coding: utf-8 -*-
"""Worktree Manager console output: version, OS detection, step/success/warning/error messages"""

import platform
import sys

VERSION = "1.1.0"

# Detect Windows environment
IS_WINDOWS = platform.system() == 'Windows'


def print_header():
  """Print header"""
  print("━" * 60)
  print(f"🌿 Git Worktree Manager v{VERSION}")
  print("━" * 60)
  print()


def print_step(emoji: str, message: str):
  """Print step message"""
  print(f"{emoji} {message}")


def print_error(message: str):
  """Print error message"""
  print(f"❌ Error: {message}", file=sys.stderr)


def print_success(message: str):
  """Print success message"""
  print(f"✅ {message}")


def print_info(message: str):
  """Print info message"""
  print(f"ℹ️  {message}")


def print_warning(message: str):
  """Print warning message"""
  print(f"⚠️  {message}")
