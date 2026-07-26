#!/bin/bash
# ===================================================================
# version.json → playstore-wizard.html 동기화 스크립트
# ===================================================================
#
# version.json의 내용을 HTML의 <script id="versionJson"> 블록에 그대로 주입한다.
# 마법사 UI의 "변경 이력" 모달이 이 블록을 읽으므로, version.json을 고친 뒤
# 반드시 이 스크립트를 실행해야 화면에 반영된다.
#
# 사용법: ./version-sync.sh
#
# ⚠️ 이 파일은 3종 마법사(testflight/playstore/firebase)가 공유하는 정본이다.
#    한 곳을 고치면 _shared/check-consistency.py가 나머지 불일치를 잡아낸다.
# ===================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION_FILE="$SCRIPT_DIR/version.json"
INDEX_FILE="$SCRIPT_DIR/playstore-wizard.html"

# 파일 존재 확인
if [ ! -f "$VERSION_FILE" ]; then
    echo "❌ version.json 파일을 찾을 수 없습니다: $VERSION_FILE"
    exit 1
fi

if [ ! -f "$INDEX_FILE" ]; then
    echo "❌ playstore-wizard.html 파일을 찾을 수 없습니다: $INDEX_FILE"
    exit 1
fi

# Python 탐색 — Windows Git Bash에는 python3가 없고 python만 있는 경우가 많다
PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -z "$PYTHON" ]; then
    echo "❌ Python을 찾을 수 없습니다. python3 또는 python이 PATH에 있어야 합니다."
    exit 1
fi

# 현재 버전 출력 (grep -P 등 GNU 전용 옵션 사용 금지 — macOS는 BSD grep)
CURRENT_VERSION=$(grep '"version"' "$VERSION_FILE" | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/')
echo "📦 동기화할 버전: v$CURRENT_VERSION"

"$PYTHON" - "$VERSION_FILE" "$INDEX_FILE" << 'EOF'
import json
import re
import sys

version_file, index_file = sys.argv[1], sys.argv[2]

with open(version_file, encoding='utf-8') as f:
    version_content = f.read()

# 주입 전 JSON 유효성 검증 — 깨진 JSON을 넣으면 마법사의 변경 이력이 조용히 죽는다
try:
    json.loads(version_content)
except json.JSONDecodeError as e:
    print(f"❌ version.json이 올바른 JSON이 아닙니다: {e}")
    sys.exit(1)

with open(index_file, encoding='utf-8') as f:
    index_content = f.read()

pattern = r'(<script type="application/json" id="versionJson">)[\s\S]*?(</script>)'
if not re.search(pattern, index_content):
    print("❌ HTML에서 versionJson 블록을 찾을 수 없습니다.")
    sys.exit(1)

# 치환값의 백슬래시가 re.sub의 이스케이프로 해석되지 않도록 함수 형태로 넘긴다
new_content = re.sub(
    pattern,
    lambda m: m.group(1) + "\n" + version_content + "\n    " + m.group(2),
    index_content,
    count=1,
)

with open(index_file, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ 버전 정보 동기화 완료!")
print(f"   - version.json → {index_file.split('/')[-1]}")
EOF
