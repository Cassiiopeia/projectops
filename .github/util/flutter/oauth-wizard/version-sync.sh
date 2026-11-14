#!/bin/bash
# ===================================================================
# version.json → oauth-wizard.html sync script
# ===================================================================
#
# Injects the content of version.json as is into the HTML <script id="versionJson"> block.
# The wizard UI's "Changelog" modal reads this block, so after editing version.json
# you must run this script for the change to show on screen.
#
# Usage: ./version-sync.sh
#
# ⚠️ This file is the shared source for the Flutter wizards (testflight/playstore/firebase/oauth).
#    Edit one and _shared/check-consistency.py catches the remaining mismatches.
# ===================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION_FILE="$SCRIPT_DIR/version.json"
INDEX_FILE="$SCRIPT_DIR/oauth-wizard.html"

# Check the file exists
if [ ! -f "$VERSION_FILE" ]; then
    echo "❌ version.json not found: $VERSION_FILE"
    exit 1
fi

if [ ! -f "$INDEX_FILE" ]; then
    echo "❌ oauth-wizard.html not found: $INDEX_FILE"
    exit 1
fi

# Find Python — Windows Git Bash often has only python, not python3
PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -z "$PYTHON" ]; then
    echo "❌ Python not found. python3 or python must be on PATH."
    exit 1
fi

# Print the current version (no GNU-only options such as grep -P — macOS has BSD grep)
CURRENT_VERSION=$(grep '"version"' "$VERSION_FILE" | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/')
echo "📦 Syncing version: v$CURRENT_VERSION"

"$PYTHON" - "$VERSION_FILE" "$INDEX_FILE" << 'EOF'
import json
import re
import sys

version_file, index_file = sys.argv[1], sys.argv[2]

with open(version_file, encoding='utf-8') as f:
    version_content = f.read()

# Validate the JSON before injecting — broken JSON silently kills the wizard's changelog
try:
    json.loads(version_content)
except json.JSONDecodeError as e:
    print(f"❌ version.json is not valid JSON: {e}")
    sys.exit(1)

with open(index_file, encoding='utf-8') as f:
    index_content = f.read()

pattern = r'(<script type="application/json" id="versionJson">)[\s\S]*?(</script>)'
if not re.search(pattern, index_content):
    print("❌ versionJson block not found in the HTML.")
    sys.exit(1)

# Pass the replacement as a function so backslashes are not read as re.sub escapes
new_content = re.sub(
    pattern,
    lambda m: m.group(1) + "\n" + version_content + "\n    " + m.group(2),
    index_content,
    count=1,
)

with open(index_file, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ Version info synced!")
print(f"   - version.json → {index_file.split('/')[-1]}")
EOF
