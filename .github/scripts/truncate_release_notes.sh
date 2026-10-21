#!/bin/bash
# ===================================================================
# truncate_release_notes.sh — Python 위임 shim (v4.2, 이슈 #448)
# ===================================================================
#
# 로직은 truncate_release_notes.py로 이전되었다. 이 파일은 기존
# 워크플로우 호출 계약을 보존하는 위임 shim이다:
#   bash ./.github/scripts/truncate_release_notes.sh <입력> <한도> <모드> [출력]
#
# 계약: 어떤 경우에도 비정상 종료하지 않는다(exit 0) — 배포 파이프라인 보호.
# ===================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
if [ -z "$PYTHON" ]; then
  echo "⚠️ truncate_release_notes: Python not found. Keeping the original without truncation."
  exit 0
fi

PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPT_DIR/truncate_release_notes.py" "$@"
exit 0
