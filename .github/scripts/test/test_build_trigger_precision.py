"""빌드 트리거가 명령을 정확히 읽는지 실제로 실행해 확인한다 (#647).

워크플로의 github-script 본문을 꺼내 node 로 돌린다. 문자열 검색으로는
"happy 에 반응하는가", "API 오류를 이슈로 단정하는가" 같은 동작을 확인할 수 없다.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github/workflows/project-types/flutter/PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node 필요")

RUNNER = r"""
const [script, ctxJson, envJson, ghJson] = process.argv.slice(1);
const ctx = JSON.parse(ctxJson);
const cfg = JSON.parse(ghJson);
const outputs = {};
const core = { setOutput: (k, v) => { outputs[k] = v; } };
let calls = 0;
const github = { rest: {
  pulls: { get: async () => {
    const step = cfg.pulls[Math.min(calls++, cfg.pulls.length - 1)];
    if (step.err) { const e = new Error(step.err.msg || 'x'); e.status = step.err.status; throw e; }
    return { data: step.ok };
  } },
  issues: { listComments: async () => ({ data: cfg.comments || [] }) },
} };
process.env = { ...process.env, ...JSON.parse(envJson) };
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
// 재시도 대기를 줄여 테스트가 빨리 끝나게 한다
global.setTimeout = (fn) => { fn(); return 0; };
new AsyncFunction('github', 'context', 'core', script)(github, ctx, core)
  .then(() => console.log(JSON.stringify({ outputs, calls })));
"""


def step_script(name):
    d = yaml.safe_load(WF.read_text(encoding="utf-8"))
    for st in d["jobs"]["trigger-builds"]["steps"]:
        if st.get("name") == name:
            return st["with"]["script"], st
    raise AssertionError(name)


def run(script, ctx, env=None, gh=None):
    r = subprocess.run(["node", "-e", RUNNER, script, json.dumps(ctx), json.dumps(env or {}),
                        json.dumps(gh or {"pulls": [{"err": {"status": 404}}]})],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def build_type(body):
    script, _ = step_script("빌드 타입 판별")
    ctx = {"payload": {"comment": {"body": body}, "issue": {"number": 1}}, "repo": {"owner": "o", "repo": "r"}}
    return run(script, ctx)["outputs"]


@pytest.mark.parametrize("body,expected", [
    ("@projectops app build", "app"),
    ("@projectops build app", "app"),
    ("@projectops apk build", "apk"),
    ("@projectops IOS build feature/x", "ios"),
])
def test_valid_commands(body, expected):
    assert build_type(body)["buildType"] == expected


@pytest.mark.parametrize("body", [
    "@projectops happy to build this",          # app 이 부분 문자열로만 존재
    "@projectops build application 배포 설명",
    "@projectops ios 는 나중에 build 하자",       # 두 단어가 붙어 있지 않다
    "그냥 build app 이야기",                      # 멘션 없음
])
def test_non_commands_are_ignored(body):
    assert build_type(body)["buildType"] == ""


def test_steps_after_detection_are_gated_on_command():
    for name in ("댓글에 👀 리액션 추가", "PR/이슈 정보 확인 및 추출"):
        _, st = step_script(name)
        assert "steps.build_type.outputs.buildType != ''" in st["if"], name
    _, st = step_script("브랜치 정보를 찾을 수 없는 경우 에러 댓글 작성")
    assert "steps.build_type.outputs.buildType != ''" in st["if"]


def source_info(gh, custom=""):
    script, _ = step_script("PR/이슈 정보 확인 및 추출")
    ctx = {"payload": {"issue": {"number": 7}}, "repo": {"owner": "o", "repo": "r"}}
    return run(script, ctx, {"CUSTOM_BRANCH": custom}, gh)


PR_OK = {"number": 7, "head": {"ref": "20260101_#7_x", "sha": "abc"}}


def test_pr_found():
    r = source_info({"pulls": [{"ok": PR_OK}]})
    assert r["outputs"]["sourceType"] == "PR" and r["outputs"]["found"] == "true"


def test_404_means_issue():
    r = source_info({"pulls": [{"err": {"status": 404}}]}, custom="feature/x")
    assert r["outputs"]["sourceType"] == "ISSUE" and r["outputs"]["found"] == "true"
    assert r["calls"] == 1  # 404 는 재시도하지 않는다


def test_transient_error_is_retried_then_pr():
    r = source_info({"pulls": [{"err": {"status": 502}}, {"ok": PR_OK}]})
    assert r["outputs"]["sourceType"] == "PR" and r["calls"] == 2


def test_persistent_api_error_is_failure_not_issue():
    r = source_info({"pulls": [{"err": {"status": 500, "msg": "boom"}}]}, custom="feature/x")
    assert r["outputs"]["found"] == "false"
    assert "sourceType" not in r["outputs"], "API 오류를 이슈로 단정하면 안 된다"
    assert r["calls"] == 3
