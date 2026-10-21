#!/bin/bash
# ============================================
# version.json → projects-sync-wizard.html 동기화 스크립트
# 사용법: ./version-sync.sh
# ============================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION_FILE="$SCRIPT_DIR/version.json"
INDEX_FILE="$SCRIPT_DIR/projects-sync-wizard.html"

# 파일 존재 확인
if [ ! -f "$VERSION_FILE" ]; then
    echo "❌ version.json not found: $VERSION_FILE"
    exit 1
fi

if [ ! -f "$INDEX_FILE" ]; then
    echo "❌ projects-sync-wizard.html not found: $INDEX_FILE"
    exit 1
fi

# 현재 버전 출력
CURRENT_VERSION=$(grep '"version"' "$VERSION_FILE" | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/')
echo "📦 Syncing version: v$CURRENT_VERSION"

# Python을 사용해 안전하게 교체
python3 - "$VERSION_FILE" "$INDEX_FILE" << 'EOF'
import sys
import re

version_file = sys.argv[1]
index_file = sys.argv[2]

# version.json 읽기
with open(version_file, 'r', encoding='utf-8') as f:
    version_content = f.read()

# projects-sync-wizard.html 읽기
with open(index_file, 'r', encoding='utf-8') as f:
    index_content = f.read()

# 정규식으로 versionJson 스크립트 영역 교체
pattern = r'(<script type="application/json" id="versionJson">)[\s\S]*?(</script>)'
replacement = r'\1\n' + version_content + r'\n    \2'

new_content = re.sub(pattern, replacement, index_content, count=1)

# 저장
with open(index_file, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ Version info synced!")
print("   - version.json → projects-sync-wizard.html")
EOF
