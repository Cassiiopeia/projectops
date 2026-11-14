#!/bin/bash
# ===================================================================
# template_initializer.sh — Python delegating shim (v4.2, issue #448)
# ===================================================================
#
# The logic moved to template_initializer.py (cross-platform, stdlib only).
# This file is a delegating shim that keeps the call contract of the existing
# workflow (PROJECT-TEMPLATE-INITIALIZER):
#   ./.github/scripts/template_initializer.sh --version 1.0.0 --type spring
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
    echo "❌ Python (3.x) is required. template_initializer runs on Python since v4.2." >&2
    echo "   It is preinstalled on GitHub Actions ubuntu-latest." >&2
    exit 1
fi

PYTHONIOENCODING=utf-8 exec "$PYTHON_BIN" "$SCRIPT_DIR/template_initializer.py" "$@"
