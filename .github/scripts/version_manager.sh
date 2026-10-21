#!/bin/bash
# ===================================================================
# version_manager.sh — Python 위임 shim (v4.2, 이슈 #448)
# ===================================================================
#
# 로직은 version_manager.py(크로스 플랫폼, stdlib 전용)로 이전되었다.
# 이 파일은 기존 워크플로우/스크립트의 호출 계약을 보존하는 위임 shim이다:
#   ./.github/scripts/version_manager.sh get   →   python version_manager.py get
#
# stdout(결과값)/stderr(로그)/종료코드 계약은 .py가 동일하게 유지한다.
# Windows(PowerShell/CMD)에서는 python .github/scripts/version_manager.py 를
# 직접 실행해도 된다. yq/jq는 더 이상 필요 없다.
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
