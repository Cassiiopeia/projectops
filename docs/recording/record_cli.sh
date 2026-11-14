#!/usr/bin/env bash
# CLI demo GIF recording: real run on a sample Spring project with the working-tree CLI and templates (#976)
# Usage: docs/recording/record_cli.sh en|ko
# Output: docs/images/cli-wizard.gif, cli-oneshot.gif (ko is *.ko.gif)
# Needs: vhs (brew install vhs), node 20.12+, rsync, git
set -euo pipefail

LANG_CODE=${1:-}
case "$LANG_CODE" in
  en) FILE_SUFFIX="";  FONT_FAMILY_LINE="" ;;
  # Monospace font with correct Hangul width (falls back to the vhs default font)
  ko) FILE_SUFFIX=".ko"; FONT_FAMILY_LINE='Set FontFamily "D2Coding"' ;;
  *) echo "usage: $0 en|ko" >&2; exit 2 ;;
esac
command -v vhs >/dev/null 2>&1 || { echo "vhs not found: brew install vhs" >&2; exit 1; }

RECORDING_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$RECORDING_DIR/../.." && pwd)
OUTPUT_DIR="$REPO_ROOT/docs/images"
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/projectops-recording.XXXXXX")
trap 'rm -rf "$WORK_DIR"' EXIT

# Template snapshot: tracked + untracked (non-ignored) files > uncommitted changes show in the recording
# (-z: NUL-separated so Korean paths are not quoted)
(cd "$REPO_ROOT" && git ls-files -z -co --exclude-standard) \
  | rsync -a --from0 --files-from=- "$REPO_ROOT/" "$WORK_DIR/template/"

# Sample Spring project (main branch, 1 commit)
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
# Local bare remote so the wizard's develop push question succeeds (no network needed)
# (remote folder name = repo name > service name default comes out as demo-app)
git init -q --bare "$WORK_DIR/wizard/remote/demo-app.git"
git -C "$WORK_DIR/wizard/demo-app" remote add origin "$WORK_DIR/wizard/remote/demo-app.git"
git -C "$WORK_DIR/wizard/demo-app" push -q -u origin main
create_sample_project "$WORK_DIR/oneshot/demo-app"

# Fill the tape ({{...}}) then record
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
