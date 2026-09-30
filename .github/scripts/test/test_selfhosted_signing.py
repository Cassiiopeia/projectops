"""셀프호스트 Android 배포의 서명 · 업로드 경로 회귀 테스트 (#650).

실사고: SMB_PATH_ANDROID 를 쓰면서 정의가 없어 빈 문자열로 평가됐고,
릴리스 APK 가 항상 디버그 키로 서명됐다. 기존 사용자의 동작은 유지해야 하므로
기본값은 "지금 실제 동작과 같은 값"(빈 경로 + 키 없으면 디버그 서명)이다.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github/workflows/project-types/flutter/PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml"


def _doc():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def _signing_step():
    steps = _doc()["jobs"]["build-android"]["steps"]
    return next(s for s in steps if "key.properties" in s.get("name", ""))


def test_smb_path_android_defined_with_empty_default():
    env = _doc()["env"]
    assert "SMB_PATH_ANDROID" in env
    assert env["SMB_PATH_ANDROID"] == ""


def test_release_signing_is_opt_in_via_variable():
    step = _signing_step()
    # 옵트인 변수는 vars 로 받아 env 로 전달한다 (스크립트에 직접 삽입 금지)
    assert "vars.ANDROID_SELFHOSTED_RELEASE_SIGNING" in step["env"]["ANDROID_SELFHOSTED_RELEASE_SIGNING"]
    assert "${{ vars." not in step["run"]
    run = step["run"]
    # 값이 정확히 true 일 때만 릴리스 경로
    assert re.search(r'if\s+\[\s+"\$ANDROID_SELFHOSTED_RELEASE_SIGNING"\s+=\s+"true"\s+\]', run)


def test_default_path_is_debug_signing_with_warning():
    run = _signing_step()["run"]
    head, _, tail = run.partition("else")
    # 옵트인 분기(head)에는 디버그 키가 없고, 기본 분기(tail)에 디버그 키와 경고가 있다
    assert "androiddebugkey" not in head
    assert "androiddebugkey" in tail
    assert "::warning::" in tail
    assert "ANDROID_SELFHOSTED_RELEASE_SIGNING" in tail


def test_opt_in_with_missing_secret_fails():
    head = _signing_step()["run"].partition("else")[0]
    assert "::error::" in head
    assert "exit 1" in head


def test_secrets_passed_via_env_not_inlined_in_script():
    step = _signing_step()
    assert "${{ secrets." not in step["run"]
    env = step.get("env", {})
    for name in ("RELEASE_KEYSTORE_BASE64", "RELEASE_KEYSTORE_PASSWORD",
                 "RELEASE_KEY_ALIAS", "RELEASE_KEY_PASSWORD", "DEBUG_KEYSTORE"):
        assert name in env, name
        assert f"secrets.{name}" in env[name]


def test_release_values_not_echoed():
    run = _signing_step()["run"]
    # base64 -d 로 파이프하는 echo 는 파일로 가므로 제외하고, 화면에 찍는 echo 만 본다
    for line in run.splitlines():
        if line.lstrip().startswith("echo") and "base64 -d" not in line:
            assert not re.search(r"\$\{?RELEASE_", line), line
    assert "cat android/key.properties" not in run
