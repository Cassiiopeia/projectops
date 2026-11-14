#!/bin/bash
# ===================================================================
# truncate_release_notes.sh — Python delegating shim (v4.2, issue #448)
# ===================================================================
#
# The logic moved to truncate_release_notes.py. This file is a delegating shim that keeps
# the existing workflow call contract:
#   bash ./.github/scripts/truncate_release_notes.sh <input> <limit> <mode> [output]
#
# Contract: never exits abnormally (exit 0) — protects the deploy pipeline.
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
