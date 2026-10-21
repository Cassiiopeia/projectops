#!/usr/bin/env python3
# Firebase wizard setup script - Python 시나리오 테스트
# 사용법: python3 setup-script-test.py
# (구 bash 시나리오 테스트를 포팅 — 시나리오/기대값 동일, 대상은 firebase-wizard.py setup)
import filecmp
import glob
import os
import shutil
import subprocess
import sys
import tempfile

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WIZARD_DIR = os.path.dirname(SCRIPT_DIR)
SETUP = os.path.join(WIZARD_DIR, "firebase-wizard.py")
FIXTURES = os.path.join(SCRIPT_DIR, "fixtures")

PASS = 0
FAIL = 0
FAIL_LOG = []


def run_setup(*args):
    """firebase-wizard.py setup 실행 (stdout+stderr 합쳐 반환)"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, SETUP, "setup"] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, env=env,
    )
    return proc.stdout.decode("utf-8", errors="replace")


def assert_contains(needle, haystack, label):
    global PASS, FAIL
    if needle in haystack:
        PASS += 1
        print("  ✅ %s" % label)
    else:
        FAIL += 1
        FAIL_LOG.append("%s — 기대 문자열 '%s' 누락" % (label, needle))
        print("  ❌ %s" % label)


def assert_file_unchanged(original, actual, label):
    global PASS, FAIL
    if filecmp.cmp(original, actual, shallow=False):
        PASS += 1
        print("  ✅ %s" % label)
    else:
        FAIL += 1
        FAIL_LOG.append("%s — 파일이 변경됨" % label)
        print("  ❌ %s" % label)


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def setup_workspace():
    ws = tempfile.mkdtemp()
    wf = os.path.join(ws, ".github", "workflows")
    os.makedirs(wf)
    for fixture in glob.glob(os.path.join(FIXTURES, "*.yaml")):
        shutil.copy(fixture, wf)
    return ws


def cleanup_workspace(ws):
    shutil.rmtree(ws, ignore_errors=True)


NEW_APP_ID = "1:905325245238:android:86db75164e0df29a1f3997"
NEW_TESTER = "romrom"

print("=== 시나리오 1: placeholder → 새 값 치환 ===")
ws = setup_workspace()
out = run_setup("--project-path", ws, "--app-id", NEW_APP_ID,
                "--tester-group", NEW_TESTER, "--non-interactive", "--no-backup")
content = read_file(os.path.join(ws, ".github", "workflows", "workflow-with-placeholders.yaml"))
assert_contains(NEW_APP_ID, content, "placeholder fixture에 새 APP_ID 적용")
assert_contains(NEW_TESTER, content, "placeholder fixture에 새 TESTER 적용")
cleanup_workspace(ws)

print("=== 시나리오 2: 키 없는 파일은 변경되지 않음 ===")
ws = setup_workspace()
run_setup("--project-path", ws, "--app-id", NEW_APP_ID,
          "--tester-group", NEW_TESTER, "--non-interactive", "--no-backup")
assert_file_unchanged(
    os.path.join(FIXTURES, "workflow-without-keys.yaml"),
    os.path.join(ws, ".github", "workflows", "workflow-without-keys.yaml"),
    "키 없는 fixture 변경 없음")
cleanup_workspace(ws)

print("=== 시나리오 3: 이미 같은 값은 SKIP ===")
ws = setup_workspace()
out = run_setup("--project-path", ws, "--app-id", NEW_APP_ID,
                "--tester-group", NEW_TESTER, "--non-interactive", "--no-backup")
assert_contains("already the same value", out, "같은 값 SKIP 메시지 출력")
content = read_file(os.path.join(ws, ".github", "workflows", "workflow-mixed.yaml"))
assert_contains(NEW_APP_ID, content, "mixed fixture APP_ID는 치환됨")
cleanup_workspace(ws)

print("=== 시나리오 4: 다른 값 + non-interactive → SKIP ===")
ws = setup_workspace()
out = run_setup("--project-path", ws, "--app-id", NEW_APP_ID,
                "--tester-group", NEW_TESTER, "--non-interactive", "--no-backup")
ORIGINAL_APP_ID = "1:111111111111:android:aaaaaaaaaaaaaaaaaaaaaa"
content = read_file(os.path.join(ws, ".github", "workflows", "workflow-with-real-values.yaml"))
assert_contains(ORIGINAL_APP_ID, content, "real-values fixture APP_ID는 SKIP되어 보존")
assert_contains("old-group", content, "real-values fixture TESTER_GROUP는 SKIP되어 보존")
cleanup_workspace(ws)

print("=== 시나리오 5: --dry-run 시 파일 변경 없음 ===")
ws = setup_workspace()
run_setup("--project-path", ws, "--app-id", NEW_APP_ID,
          "--tester-group", NEW_TESTER, "--non-interactive", "--no-backup", "--dry-run")
assert_file_unchanged(
    os.path.join(FIXTURES, "workflow-with-placeholders.yaml"),
    os.path.join(ws, ".github", "workflows", "workflow-with-placeholders.yaml"),
    "dry-run 시 placeholder fixture 변경 없음")
cleanup_workspace(ws)

print("=== 시나리오 6: 백업 파일 생성 ===")
ws = setup_workspace()
run_setup("--project-path", ws, "--app-id", NEW_APP_ID,
          "--tester-group", NEW_TESTER, "--non-interactive")
bak_count = len(glob.glob(os.path.join(ws, ".github", "workflows", "*.bak.*")))
if bak_count >= 2:
    PASS += 1
    print("  ✅ 백업 파일 자동 생성됨 (%d개)" % bak_count)
else:
    FAIL += 1
    FAIL_LOG.append("백업 파일이 충분히 생성되지 않음 (%d개)" % bak_count)
    print("  ❌ 백업 파일 자동 생성")
cleanup_workspace(ws)

print("=== 시나리오 7: --no-backup 시 백업 파일 미생성 ===")
ws = setup_workspace()
run_setup("--project-path", ws, "--app-id", NEW_APP_ID,
          "--tester-group", NEW_TESTER, "--non-interactive", "--no-backup")
bak_count = len(glob.glob(os.path.join(ws, ".github", "workflows", "*.bak.*")))
if bak_count == 0:
    PASS += 1
    print("  ✅ --no-backup 시 백업 미생성")
else:
    FAIL += 1
    FAIL_LOG.append("--no-backup인데 백업 파일이 생성됨 (%d개)" % bak_count)
    print("  ❌ --no-backup")
cleanup_workspace(ws)

print("=== 시나리오 8: .github/workflows 폴더 없을 때 abort ===")
ws = tempfile.mkdtemp()
out = run_setup("--project-path", ws, "--app-id", NEW_APP_ID,
                "--tester-group", NEW_TESTER, "--non-interactive", "--no-backup")
assert_contains("workflows", out, "workflows 폴더 없음 에러 메시지")
cleanup_workspace(ws)

print("=== 시나리오 9: 들여쓰기 보존 (라인 단위 처리 검증) ===")
ws = setup_workspace()
run_setup("--project-path", ws, "--app-id", NEW_APP_ID,
          "--tester-group", NEW_TESTER, "--non-interactive", "--no-backup")
content = read_file(os.path.join(ws, ".github", "workflows", "workflow-with-placeholders.yaml"))
line = "\n".join(l for l in content.split("\n") if "FIREBASE_APP_ID" in l)
assert_contains("  FIREBASE_APP_ID", line, "들여쓰기 2칸 보존")
cleanup_workspace(ws)

print("=== 시나리오 10: 단어 경계 (FIREBASE_APP_ID_DEV 같은 비슷한 키 보호) ===")
ws = tempfile.mkdtemp()
wf = os.path.join(ws, ".github", "workflows")
os.makedirs(wf)
with open(os.path.join(wf, "edge.yaml"), "w", encoding="utf-8", newline="\n") as f:
    f.write('env:\n'
            '  FIREBASE_APP_ID: "{FIREBASE_APP_ID}"\n'
            '  FIREBASE_APP_ID_DEV: "{FIREBASE_APP_ID}"\n')
run_setup("--project-path", ws, "--app-id", NEW_APP_ID,
          "--tester-group", NEW_TESTER, "--non-interactive", "--no-backup")
content = read_file(os.path.join(wf, "edge.yaml"))
id_dev_line = "\n".join(l for l in content.split("\n") if "FIREBASE_APP_ID_DEV" in l)
assert_contains("{FIREBASE_APP_ID}", id_dev_line,
                "FIREBASE_APP_ID_DEV는 단어 경계 매칭으로 변경되지 않음")
cleanup_workspace(ws)

print()
print("====================")
print("PASS: %d" % PASS)
print("FAIL: %d" % FAIL)
if FAIL > 0:
    print()
    print("실패 항목:")
    for msg in FAIL_LOG:
        print("  - %s" % msg)
    sys.exit(1)
sys.exit(0)
