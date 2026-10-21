#!/bin/bash
# version_manager project_paths(모노레포 경로) 테스트 스위트
# 실행: bash .github/scripts/test/test_version_manager_paths.sh
# v4.2(#448): version_manager가 Python으로 이전 — yq/jq 불필요, 검증도 python으로 수행
set -u
SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/version_manager.sh"
PASS=0
FAIL=0

PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "SKIP: python 필요"; exit 0; }

chk() {
  local d="$1" a="$2" e="$3"
  if [ "$a" = "$e" ]; then
    echo "  PASS: $d"; PASS=$((PASS+1))
  else
    echo "  FAIL: $d (got: '$a', want: '$e')"; FAIL=$((FAIL+1))
  fi
}

# 파일에서 값 추출 헬퍼 (yq/jq 대체 — python 원라이너)
pubspec_version() { "$PYTHON" -c "import re,sys;print(re.search(r'^version:\s*(\S+)',open(sys.argv[1],encoding='utf-8').read(),re.M).group(1))" "$1"; }
json_version()    { "$PYTHON" -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))['version'])" "$1"; }
toml_version()    { "$PYTHON" -c "import re,sys;print(re.search(r'^version = \"([^\"]+)\"',open(sys.argv[1],encoding='utf-8').read(),re.M).group(1))" "$1"; }
yml_version()     { "$PYTHON" -c "import re,sys;print(re.search(r'^version:\s*\"?([0-9.]+)\"?',open(sys.argv[1],encoding='utf-8').read(),re.M).group(1))" "$1"; }

new_workdir() {
  WORK=$(mktemp -d)
  cd "$WORK" || exit 1
}

echo "=== (1) v4.1.0 breaking: legacy 단수 키만 있으면 명시적 실패 ==="
new_workdir
cat > version.yml << 'EOF'
version: "0.0.2"
version_code: 5
project_type: "flutter"
EOF
printf 'name: demo\nversion: 0.0.1+1\n' > pubspec.yaml
OUT=$(bash "$SCRIPT" sync 2>&1)
RC=$?
chk "legacy 형식 → exit 1" "$RC" "1"
echo "$OUT" | grep -q "project_types" && chk "전환 안내 출력" "1" "1" || chk "전환 안내 출력" "0" "1"
chk "pubspec 미변경 (조용한 오작동 방지)" "$(pubspec_version pubspec.yaml)" "0.0.1+1"

echo "=== (1-2) 배열 단독 + 루트 flutter sync (SSOT 정상 경로) ==="
new_workdir
cat > version.yml << 'EOF'
version: "0.0.2"
version_code: 5
project_types: ["flutter"]
EOF
printf 'name: demo\nversion: 0.0.1+1\n' > pubspec.yaml
bash "$SCRIPT" sync >/dev/null 2>&1
chk "루트 pubspec 동기화" "$(pubspec_version pubspec.yaml)" "0.0.2+5"

echo "=== (1-3) 배열 + 잔존 단수 키: 단수 무시(경고)하고 정상 동작 ==="
new_workdir
cat > version.yml << 'EOF'
version: "0.0.2"
version_code: 5
project_types: ["flutter"]
project_type: "spring"
EOF
printf 'name: demo\nversion: 0.0.1+1\n' > pubspec.yaml
OUT=$(bash "$SCRIPT" sync 2>&1)
chk "exit 0" "$?" "0"
chk "배열 기준으로 pubspec 동기화 (단수 spring 무시)" "$(pubspec_version pubspec.yaml)" "0.0.2+5"
echo "$OUT" | grep -q "ignored" && chk "단수 키 무시 경고 출력" "1" "1" || chk "단수 키 무시 경고 출력" "0" "1"

echo "=== (2) 모노레포: project_paths 있는 멀티타입 sync ==="
new_workdir
cat > version.yml << 'EOF'
version: "0.0.9"
version_code: 5
project_types: ["flutter", "react", "python"]
project_paths:
  flutter: "app"
  react: "client"
  python: "ai"
EOF
mkdir -p app client ai
printf 'name: demo\nversion: 0.0.1+1\n' > app/pubspec.yaml
printf '{"name":"demo","version":"0.0.1"}\n' > client/package.json
printf '[project]\nname = "demo"\nversion = "0.0.1"\n' > ai/pyproject.toml
bash "$SCRIPT" sync >/dev/null 2>&1
chk "app/pubspec.yaml" "$(pubspec_version app/pubspec.yaml)" "0.0.9+5"
chk "client/package.json" "$(json_version client/package.json)" "0.0.9"
chk "ai/pyproject.toml" "$(toml_version ai/pyproject.toml)" "0.0.9"

echo "=== (3) paths 없는 멀티타입: 서브폴더 미동기화(기존 no-op) + exit 0 ==="
new_workdir
cat > version.yml << 'EOF'
version: "0.0.9"
version_code: 5
project_types: ["flutter", "react"]
EOF
mkdir -p app client
printf 'name: demo\nversion: 0.0.1+1\n' > app/pubspec.yaml
printf '{"name":"demo","version":"0.0.1"}\n' > client/package.json
bash "$SCRIPT" sync >/dev/null 2>&1
chk "exit 0" "$?" "0"
chk "app/pubspec 그대로" "$(pubspec_version app/pubspec.yaml)" "0.0.1+1"
chk "client/package.json 그대로" "$(json_version client/package.json)" "0.0.1"

echo "=== (4) 경로에 마커 없음: 경고 + skip + exit 0 ==="
new_workdir
cat > version.yml << 'EOF'
version: "0.0.9"
version_code: 5
project_types: ["flutter"]
project_paths:
  flutter: "nope"
EOF
OUT=$(bash "$SCRIPT" sync 2>&1)
chk "exit 0" "$?" "0"
echo "$OUT" | grep -q "skipping" && chk "경고 출력" "1" "1" || chk "경고 출력" "0" "1"

echo "=== (5) increment: 경로 따라 patch 증가 ==="
new_workdir
cat > version.yml << 'EOF'
version: "0.0.9"
version_code: 5
project_types: ["flutter", "react"]
project_paths:
  flutter: "app"
  react: "client"
EOF
mkdir -p app client
printf 'name: demo\nversion: 0.0.9+5\n' > app/pubspec.yaml
printf '{"name":"demo","version":"0.0.9"}\n' > client/package.json
bash "$SCRIPT" increment >/dev/null 2>&1
chk "version.yml 증가" "$(yml_version version.yml)" "0.0.10"
chk "app/pubspec 증가" "$(pubspec_version app/pubspec.yaml | cut -d'+' -f1)" "0.0.10"
chk "client/package.json 증가" "$(json_version client/package.json)" "0.0.10"

echo "=== (5-2) increment: version_code 함께 증가 + stdout 마지막 줄 계약 ==="
new_workdir
cat > version.yml << 'EOF'
version: "1.2.3"
version_code: 7
project_types: ["basic"]
EOF
NEW_V=$(bash "$SCRIPT" increment 2>/dev/null | tail -n 1)
chk "increment 결과(stdout tail)" "$NEW_V" "1.2.4"
CODE=$(bash "$SCRIPT" get-code 2>/dev/null | tail -n 1)
chk "version_code 8로 증가" "$CODE" "8"

echo "=== (6) spring 잘못된 경로 + increment: 경고 + exit 0 ==="
new_workdir
cat > version.yml << 'EOF'
version: "0.0.9"
version_code: 5
project_types: ["spring"]
project_paths:
  spring: "nope"
EOF
OUT=$(bash "$SCRIPT" increment 2>&1)
RC=$?
chk "exit 0" "$RC" "0"
echo "$OUT" | grep -q "skipping" && chk "경고 출력" "1" "1" || chk "경고 출력" "0" "1"
chk "version.yml 증가" "$(yml_version version.yml)" "0.0.10"

echo "=== (7) set: 지정 버전 반영 + get 동기화 유지 ==="
new_workdir
cat > version.yml << 'EOF'
version: "1.0.0"
version_code: 3
project_types: ["react"]
EOF
printf '{"name":"demo","version":"1.0.0"}\n' > package.json
bash "$SCRIPT" set 2.5.0 >/dev/null 2>&1
chk "version.yml=2.5.0" "$(yml_version version.yml)" "2.5.0"
chk "package.json=2.5.0" "$(json_version package.json)" "2.5.0"
GOT=$(bash "$SCRIPT" get 2>/dev/null | tail -n 1)
chk "get=2.5.0" "$GOT" "2.5.0"

echo "=== (8) 높은 버전 우선: 프로젝트 파일이 앞서면 version.yml을 끌어올림 ==="
new_workdir
cat > version.yml << 'EOF'
version: "1.0.0"
version_code: 3
project_types: ["react"]
EOF
printf '{"name":"demo","version":"1.4.0"}\n' > package.json
GOT=$(bash "$SCRIPT" get 2>/dev/null | tail -n 1)
chk "get=1.4.0 (높은 쪽)" "$GOT" "1.4.0"
chk "version.yml 끌어올림" "$(yml_version version.yml)" "1.4.0"

echo ""
echo "결과: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
