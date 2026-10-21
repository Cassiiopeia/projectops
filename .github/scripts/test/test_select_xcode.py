"""Xcode 자동 선택과 SDK 누락 진단 (#758).

실사고: 템플릿이 XCODE_VERSION 26.0 에 고정돼 있어, 의존성이 iOS 26.1 SDK 심볼
(NSProcessInfo.isiOSAppOnVision)을 쓰자 러너에 26.6 이 있는데도 빌드가 깨졌다.
기본은 러너 최신 정식 Xcode, 고정은 선택 사항이고 없으면 설치 목록과 함께 실패한다.
"""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github/scripts/select_xcode.py"
FLUTTER = ROOT / ".github/workflows/project-types/flutter"
IOS_WORKFLOWS = ["PROJECT-FLUTTER-CI.yaml", "PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml",
                 "PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml"]

_spec = importlib.util.spec_from_file_location("select_xcode", SCRIPT)
sx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sx)

# 실제 러너 이미지 이름 형태 (macos-26: 26.0.1 ~ 26.6, beta 포함 가능)
RUNNER_APPS = ["Xcode_26.0.app", "Xcode_26.0.1.app", "Xcode_26.6.app", "Xcode_26.10.app",
               "Xcode_27.0_beta.app", "Xcode.app"]


@pytest.fixture
def applications(tmp_path):
    for name in RUNNER_APPS:
        (tmp_path / name).mkdir()
    return tmp_path


@pytest.fixture
def github_files(tmp_path, monkeypatch):
    env_file = tmp_path / "github_env"
    summary = tmp_path / "summary"
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("XCODE_VERSION", raising=False)
    return env_file, summary


def _last_json(out: str) -> dict:
    return json.loads(out.strip().splitlines()[-1])


def test_auto_picks_highest_stable_version_numerically(applications, github_files, capsys):
    # 문자열 정렬이면 26.6 이 26.10 보다 커진다. beta 와 버전 없는 Xcode.app 은 제외
    assert sx.main(["select", "--applications-dir", str(applications)]) == 0
    result = _last_json(capsys.readouterr().out)
    assert result["version"] == "26.10"
    assert result["source"] == "latest"
    env_lines = github_files[0].read_text().splitlines()
    assert f"XCODE_DEVELOPER_DIR={applications}/Xcode_26.10.app/Contents/Developer" in env_lines
    assert f"XCODE_APP_PATH={applications}/Xcode_26.10.app" in env_lines
    assert "XCODE_LATEST_INSTALLED=26.10" in env_lines


def test_empty_pin_means_auto(applications, github_files, monkeypatch, capsys):
    monkeypatch.setenv("XCODE_VERSION", "  ")
    assert sx.main(["select", "--applications-dir", str(applications)]) == 0
    assert _last_json(capsys.readouterr().out)["version"] == "26.10"


def test_pinned_installed_version_is_used(applications, github_files, monkeypatch, capsys):
    monkeypatch.setenv("XCODE_VERSION", "26.0")
    assert sx.main(["select", "--applications-dir", str(applications)]) == 0
    result = _last_json(capsys.readouterr().out)
    assert result["version"] == "26.0" and result["source"] == "pinned"
    assert "XCODE_LATEST_INSTALLED=26.10" in github_files[0].read_text()


def test_pinned_beta_is_allowed_when_installed(applications, github_files, capsys):
    assert sx.main(["select", "--applications-dir", str(applications), "--pinned", "27.0_beta"]) == 0


def test_pinned_missing_version_fails_with_installed_list(applications, github_files, monkeypatch, capsys):
    monkeypatch.setenv("XCODE_VERSION", "25.0")
    assert sx.main(["select", "--applications-dir", str(applications)]) == 1
    out = capsys.readouterr().out
    assert "::error" in out
    assert "25.0" in out and "26.0.1" in out and "26.10" in out
    assert not github_files[0].exists(), "실패 시 job 환경을 바꾸지 않는다"


def test_no_xcode_installed_fails(tmp_path, github_files, capsys):
    assert sx.main(["select", "--applications-dir", str(tmp_path / "none")]) == 1
    assert "::error" in capsys.readouterr().out


# ── SDK 누락 진단 ─────────────────────────────────────────────
REAL_LOG = (
    "Failed to build iOS app\n"
    "ARC Semantic Issue (Xcode): No visible @interface for 'NSProcessInfo' declares the selector "
    "'isiOSAppOnVision'\n"
    "device_info_plus-13.3.0/ios/device_info_plus/Sources/device_info_plus/FPPDeviceInfoPlusPlugin.m:34:56\n"
)


def test_hint_names_latest_installed_when_older_xcode_was_used(tmp_path, github_files, monkeypatch, capsys):
    log = tmp_path / "build.log"
    log.write_text(REAL_LOG)
    monkeypatch.setenv("XCODE_SELECTED_VERSION", "26.0")
    monkeypatch.setenv("XCODE_LATEST_INSTALLED", "26.6")
    assert sx.main(["hint", "--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "::warning title=Xcode may be too old::" in out
    assert "Xcode 26.0" in out and "26.6" in out and "isiOSAppOnVision" in out
    assert "Xcode may be too old" in github_files[1].read_text()


def test_hint_when_already_latest_points_to_runner_image(tmp_path, github_files, monkeypatch, capsys):
    log = tmp_path / "build.log"
    log.write_text(REAL_LOG)
    monkeypatch.setenv("XCODE_SELECTED_VERSION", "26.6")
    monkeypatch.setenv("XCODE_LATEST_INSTALLED", "26.6")
    sx.main(["hint", "--log", str(log)])
    assert "runner image" in capsys.readouterr().out


def test_hint_stays_quiet_for_unrelated_failures(tmp_path, github_files, capsys):
    log = tmp_path / "build.log"
    log.write_text("Error: Could not resolve package dependencies\n")
    assert sx.main(["hint", "--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "::warning" not in out
    assert _last_json(out)["matched"] is False
    # 로그 파일이 없어도 진단이 실패를 덮지 않는다
    assert sx.main(["hint", "--log", str(tmp_path / "missing.log")]) == 0


# ── 워크플로우 연결 ───────────────────────────────────────────
@pytest.mark.parametrize("name", IOS_WORKFLOWS)
def test_workflows_use_the_single_selection_script(name):
    text = (FLUTTER / name).read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    # 기본값은 빈 값(자동), 경로를 직접 조립하지 않는다
    assert doc["env"]["XCODE_VERSION"] == ""
    assert "Xcode_${{" not in text
    for job in doc["jobs"].values():
        steps = job.get("steps", [])
        names = [s.get("name", "") for s in steps]
        uses_xcode = any("XCODE_DEVELOPER_DIR" in str(s.get("env", {})) or "XCODE_APP_PATH" in str(s.get("run", ""))
                         for s in steps)
        if not uses_xcode:
            continue
        # 같은 job 안에서 선택 step 이 먼저 돌아야 GITHUB_ENV 값이 있다
        select_index = names.index("Select Xcode version")
        select = steps[select_index]
        assert "select_xcode.py select --apply" in select["run"]
        assert "vars.XCODE_VERSION" in select["env"]["XCODE_VERSION"]
        first_use = next(i for i, s in enumerate(steps)
                         if "XCODE_DEVELOPER_DIR" in str(s.get("env", {})) or "XCODE_APP_PATH" in str(s.get("run", "")))
        assert select_index < first_use


@pytest.mark.parametrize("name", IOS_WORKFLOWS)
def test_ios_build_failure_runs_the_hint(name):
    doc = yaml.safe_load((FLUTTER / name).read_text(encoding="utf-8"))
    for job in doc["jobs"].values():
        steps = job.get("steps", [])
        builds = [s for s in steps if "flutter build ios" in str(s.get("run", ""))]
        for build in builds:
            assert "set -o pipefail" in build["run"], "tee 뒤에서 빌드 실패가 사라지면 안 된다"
            assert 'tee "$RUNNER_TEMP/flutter-ios-build.log"' in build["run"]
            hint = next(s for s in steps if s.get("name") == "Diagnose iOS build failure")
            assert f"steps.{build['id']}.outcome == 'failure'" in hint["if"]
            assert "select_xcode.py hint" in hint["run"]
