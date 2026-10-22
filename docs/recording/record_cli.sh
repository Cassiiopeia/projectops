#!/usr/bin/env bash
# CLI 데모 GIF 녹화: 작업 트리 CLI·템플릿으로 샘플 Spring 프로젝트에 실제 실행 (#976)
# 사용: docs/recording/record_cli.sh en|ko
# 결과: docs/images/cli-wizard.gif, cli-oneshot.gif (ko 는 *.ko.gif)
# 필요: vhs (brew install vhs), node 20.12+, rsync, git
set -euo pipefail

LANG_CODE=${1:-}
case "$LANG_CODE" in
  en) FILE_SUFFIX="";  FONT_FAMILY_LINE="" ;;
  # 한글 폭이 맞는 고정폭 글꼴 (없으면 vhs 기본 글꼴로 대체)
  ko) FILE_SUFFIX=".ko"; FONT_FAMILY_LINE='Set FontFamily "D2Coding"' ;;
  *) echo "usage: $0 en|ko" >&2; exit 2 ;;
esac
command -v vhs >/dev/null 2>&1 || { echo "vhs not found: brew install vhs" >&2; exit 1; }

RECORDING_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$RECORDING_DIR/../.." && pwd)
OUTPUT_DIR="$REPO_ROOT/docs/images"
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/projectops-recording.XXXXXX")
trap 'rm -rf "$WORK_DIR"' EXIT

# 템플릿 스냅샷: 추적 + 미추적(무시 제외) 파일 > 커밋 전 변경까지 녹화에 반영
# (-z: 한글 경로가 따옴표로 감싸이지 않게 NUL 구분)
(cd "$REPO_ROOT" && git ls-files -z -co --exclude-standard) \
  | rsync -a --from0 --files-from=- "$REPO_ROOT/" "$WORK_DIR/template/"

# 샘플 Spring 프로젝트 (main 브랜치, 커밋 1개)
create_sample_project() {
  local project_dir=$1
  mkdir -p "$project_dir/src/main/java/com/example"
  printf "plugins {\n    id 'java'\n    id 'org.springframework.boot' version '3.3.4'\n}\n\ngroup = 'com.example'\nversion = '1.0.0'\n" \
    > "$project_dir/build.gradle"
  printf 'package com.example;\n\npublic class App {}\n' > "$project_dir/src/main/java/com/example/App.java"
  git -C "$project_dir" init -q -b main
  git -C "$project_dir" add -A
  git -C "$project_dir" -c user.name=demo -c user.email=demo@example.com commit -qm "init"
}

create_sample_project "$WORK_DIR/wizard/demo-app"
# 마법사의 develop push 질문이 성공하도록 로컬 bare 원격 연결 (네트워크 불필요)
# (원격 폴더명 = 레포 이름 > 서비스 이름 기본값이 demo-app 으로 나옴)
git init -q --bare "$WORK_DIR/wizard/remote/demo-app.git"
git -C "$WORK_DIR/wizard/demo-app" remote add origin "$WORK_DIR/wizard/remote/demo-app.git"
git -C "$WORK_DIR/wizard/demo-app" push -q -u origin main
create_sample_project "$WORK_DIR/oneshot/demo-app"

# tape 치환 ({{...}}) 후 녹화
record_tape() {
  local tape_name=$1
  local rendered_tape="$WORK_DIR/$tape_name.tape"
  sed -e "s#{{OUTPUT_DIR}}#$OUTPUT_DIR#g" \
      -e "s#{{SUFFIX}}#$FILE_SUFFIX#g" \
      -e "s#{{WORK_DIR}}#$WORK_DIR#g" \
      -e "s#{{RUNNER}}#$RECORDING_DIR/run_local_projectops.mjs#g" \
      -e "s#{{LANG}}#$LANG_CODE#g" \
      -e "s#{{FONT_FAMILY_LINE}}#$FONT_FAMILY_LINE#g" \
      "$RECORDING_DIR/$tape_name.tape.tmpl" > "$rendered_tape"
  echo "[record cli] $tape_name ($LANG_CODE)"
  vhs "$rendered_tape"
}

record_tape cli-wizard
record_tape cli-oneshot
echo "[record cli] done: $OUTPUT_DIR/cli-wizard$FILE_SUFFIX.gif, cli-oneshot$FILE_SUFFIX.gif"
