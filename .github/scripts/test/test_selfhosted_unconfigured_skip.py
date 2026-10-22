"""셀프호스트(SMB) 배포 미설정 시 자동 실행 건너뛰기 (#662).

실사고: Flutter 레포에는 이 워크플로우가 항상 설치되는데, 자체 서버를 쓰지 않는 레포도
main 푸시마다 SMB 배포를 시도해 실패 런이 쌓였다. 이미 설정한 레포는 동작이 그대로여야 한다.
가드 스크립트를 실제 bash 로 돌려 경우별 판정을 본다.
"""
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github/workflows/project-types/flutter/PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml"

CONFIGURED_ENV = {"APP_ARTIFACT_NAME": "my-app", "JAVA_VERSION": "17", "SMB_PORT": "445", "SMB_SHARE": "web"}
ALL_SECRETS = {"SERVER_HOST": "nas.local", "SERVER_USER": "deploy", "SERVER_PASSWORD": "pw"}


def _doc():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def _guard_script():
    steps = _doc()["jobs"]["check-config"]["steps"]
    return next(s for s in steps if s.get("id") == "check")["run"]


def _run_guard(tmp_path, event, workflow_env, secrets):
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    env = {"PATH": os.environ.get("PATH", ""), "EVENT_NAME": event,
           "GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary),
           "SERVER_HOST": "", "SERVER_USER": "", "SERVER_PASSWORD": "", "DEPLOY_SWITCH": ""}
    env.update(workflow_env)
    env.update(secrets)
    # macOS 기본 bash 3.2 로도 돌아야 한다 (러너는 bash 5)
    bash = "/bin/bash" if Path("/bin/bash").exists() else "bash"
    result = subprocess.run([bash, "-e", "-c", _guard_script()], env=env,
                            capture_output=True, text=True)
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines() if "=" in line)
    return result, outputs


def test_template_env_has_no_dead_placeholder():
    # 쓰이지 않던 예시 값(/your-project/...)은 남겨 두지 않는다
    assert "SMB_PATH_IOS" not in _doc()["env"]
    assert "your-project" not in WF.read_text(encoding="utf-8")


def test_build_job_waits_for_guard():
    build = _doc()["jobs"]["build-android"]
    assert build["needs"] == "check-config"
    assert "needs.check-config.outputs.configured == 'true'" in build["if"]
    # 배포 job 은 빌드 job 에 묶여 있어 빌드가 건너뛰면 함께 건너뛴다
    assert _doc()["jobs"]["deploy-android"]["needs"] == "build-android"


def test_push_without_any_smb_secret_skips_successfully(tmp_path):
    result, outputs = _run_guard(tmp_path, "push", CONFIGURED_ENV, {})
    assert result.returncode == 0, result.stderr
    assert outputs["configured"] == "false"
    assert "::notice" in result.stdout and "Self-hosted" in result.stdout
    assert "Self-hosted deploy skipped" in (tmp_path / "summary").read_text()


def test_push_with_unreplaced_template_token_skips(tmp_path):
    env = dict(CONFIGURED_ENV, APP_ARTIFACT_NAME="__APP_ARTIFACT_NAME__")
    result, outputs = _run_guard(tmp_path, "push", env, ALL_SECRETS)
    assert result.returncode == 0, result.stderr
    assert outputs["configured"] == "false"
    assert "APP_ARTIFACT_NAME" in result.stdout


def test_configured_repo_runs_as_before(tmp_path):
    result, outputs = _run_guard(tmp_path, "push", CONFIGURED_ENV, ALL_SECRETS)
    assert result.returncode == 0, result.stderr
    assert outputs["configured"] == "true"
    assert "::notice" not in result.stdout


def test_partial_secrets_still_run_so_preflight_reports_the_gap(tmp_path):
    # 설정 중인 레포는 건너뛰지 않는다 — 사전 점검이 빠진 Secret 을 오류로 알려야 한다
    result, outputs = _run_guard(tmp_path, "push", CONFIGURED_ENV, {"SERVER_HOST": "nas.local"})
    assert outputs["configured"] == "true"


@pytest.mark.parametrize("event", ["workflow_dispatch", "workflow_run"])
def test_non_push_events_are_never_skipped(tmp_path, event):
    result, outputs = _run_guard(tmp_path, event, CONFIGURED_ENV, {})
    assert result.returncode == 0, result.stderr
    assert outputs["configured"] == "true"


# 저장소 변수 SELFHOSTED_DEPLOY_ENABLED 스위치 (#988)
# 실사고 가능성: 모노레포에서 Spring 배포가 SERVER_* Secret 을 이미 써서, SMB 를 안 쓰는데도
# 가드가 "설정됨"으로 보고 push 마다 SMB 배포를 돌렸다.
def _switch(value):
    return {"DEPLOY_SWITCH": value}


def test_guard_reads_the_repository_variable():
    steps = _doc()["jobs"]["check-config"]["steps"]
    guard = next(s for s in steps if s.get("id") == "check")
    assert guard["env"]["DEPLOY_SWITCH"] == "${{ vars.SELFHOSTED_DEPLOY_ENABLED }}"


@pytest.mark.parametrize("value", ["false", "FALSE", " False "])
def test_switch_false_skips_push_even_with_shared_secrets(tmp_path, value):
    result, outputs = _run_guard(tmp_path, "push", CONFIGURED_ENV, dict(ALL_SECRETS, **_switch(value)))
    assert result.returncode == 0, result.stderr
    assert outputs["configured"] == "false"
    assert "::notice" in result.stdout and "SELFHOSTED_DEPLOY_ENABLED=false" in result.stdout
    assert "Self-hosted deploy skipped" in (tmp_path / "summary").read_text()


def test_switch_unset_keeps_secret_heuristic(tmp_path):
    # 없음: 기존 동작 그대로 — Secret 있으면 실행, 없으면 건너뜀
    (tmp_path / "with").mkdir()
    (tmp_path / "without").mkdir()
    _, with_secrets = _run_guard(tmp_path / "with", "push", CONFIGURED_ENV, ALL_SECRETS)
    assert with_secrets["configured"] == "true"
    result, without = _run_guard(tmp_path / "without", "push", CONFIGURED_ENV, {})
    assert without["configured"] == "false"
    # 미설정 안내에 스위치를 함께 알린다
    assert "SELFHOSTED_DEPLOY_ENABLED=false" in result.stdout


def test_switch_true_runs_without_secret_heuristic(tmp_path):
    result, outputs = _run_guard(tmp_path, "push", CONFIGURED_ENV, _switch("true"))
    assert result.returncode == 0, result.stderr
    assert outputs["configured"] == "true"
    assert "::notice" not in result.stdout


def test_switch_true_still_skips_unreplaced_template_token(tmp_path):
    # true 는 Secret 추정만 생략 — 치환 안 된 값으로 빌드하면 어차피 실패한다
    env = dict(CONFIGURED_ENV, JAVA_VERSION="__JAVA_VERSION__")
    _, outputs = _run_guard(tmp_path, "push", env, dict(ALL_SECRETS, **_switch("true")))
    assert outputs["configured"] == "false"


def test_unknown_switch_value_warns_and_falls_back(tmp_path):
    result, outputs = _run_guard(tmp_path, "push", CONFIGURED_ENV, dict(ALL_SECRETS, **_switch("yes")))
    assert result.returncode == 0, result.stderr
    assert "::warning" in result.stdout
    assert outputs["configured"] == "true"


@pytest.mark.parametrize("value", ["false", "true", ""])
def test_switch_does_not_change_manual_runs(tmp_path, value):
    result, outputs = _run_guard(tmp_path, "workflow_dispatch", CONFIGURED_ENV, _switch(value))
    assert result.returncode == 0, result.stderr
    assert outputs["configured"] == "true"
    assert "::notice" not in result.stdout
