#!/bin/bash
# ============================================
# version.json → projects-sync-wizard.html sync script
# Usage: ./version-sync.sh
# ============================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION_FILE="$SCRIPT_DIR/version.json"
INDEX_FILE="$SCRIPT_DIR/projects-sync-wizard.html"

# Check the file exists
if [ ! -f "$VERSION_FILE" ]; then
    echo "❌ version.json not found: $VERSION_FILE"
    exit 1
fi

if [ ! -f "$INDEX_FILE" ]; then
    echo "❌ projects-sync-wizard.html not found: $INDEX_FILE"
    exit 1
fi

# Print the current version
CURRENT_VERSION=$(grep '"version"' "$VERSION_FILE" | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/')
echo "📦 Syncing version: v$CURRENT_VERSION"

# Replace safely with Python
python3 - "$VERSION_FILE" "$INDEX_FILE" << 'EOF'
import sys
import re

version_file = sys.argv[1]
index_file = sys.argv[2]

# Read version.json
with open(version_file, 'r', encoding='utf-8') as f:
    version_content = f.read()

# Read projects-sync-wizard.html
with open(index_file, 'r', encoding='utf-8') as f:
    index_content = f.read()

# Replace the versionJson script area with a regex
pattern = r'(<script type="application/json" id="versionJson">)[\s\S]*?(</script>)'
replacement = r'\1\n' + version_content + r'\n    \2'

new_content = re.sub(pattern, replacement, index_content, count=1)

# Save
with open(index_file, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ Version info synced!")
print("   - version.json → projects-sync-wizard.html")
EOF
