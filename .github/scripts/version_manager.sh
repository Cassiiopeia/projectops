#!/bin/bash
# ===================================================================
# version_manager.sh — Python delegating shim (v4.2, issue #448)
# ===================================================================
#
# The logic moved to version_manager.py (cross-platform, stdlib only).
# This file is a delegating shim that keeps the call contract of existing workflows/scripts:
#   ./.github/scripts/version_manager.sh get   →   python version_manager.py get
#
# The .py keeps the same stdout (result) / stderr (logs) / exit code contract.
# On Windows (PowerShell/CMD) you may run python .github/scripts/version_manager.py
# directly. yq/jq are no longer needed.
# ===================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON_BIN=""
for _py in python3 python; do
    _path=$(command -v "$_py" 2>/dev/null) || continue
    if "$_path" -c "import sys; sys.exit(0)" 2>/dev/null; then
        PYTHON_BIN="$_path"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Python (3.x) is required. version_manager runs on Python since v4.2." >&2
    echo "   Install: https://www.python.org/downloads/ (preinstalled on GitHub Actions ubuntu-latest)" >&2
    exit 1
fi

PYTHONIOENCODING=utf-8 exec "$PYTHON_BIN" "$SCRIPT_DIR/version_manager.py" "$@"
