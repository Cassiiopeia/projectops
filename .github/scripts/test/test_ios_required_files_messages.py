"""iOS 배포 필수 파일 누락 안내 (#785).

ExportOptions.plist · ios/fastlane/Fastfile 은 마법사가 만드는 앱별 파일이라 템플릿이 생성하지 않는다.
릴리스 TestFlight 는 ExportOptions.plist 가 없으면 아무 말 없이 exit 1 로 끝났고,
옛 Fastfile(deploy lane 없음)은 업로드 단계에서야 'Could not find lane' 으로 실패했다.
점검 스크립트를 실제 bash 로 돌려 무엇을 어떻게 만들지 알려 주는지 본다.
"""
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
FLUTTER = ROOT / ".github/workflows/project-types/flutter"
WORKFLOWS = ["PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml", "PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml"]
WIZARD = ".github/util/flutter/testflight-wizard/testflight-wizard.py setup"


def _step_script(workflow: str, step_name: str) -> str:
    doc = yaml.safe_load((FLUTTER / workflow).read_text(encoding="utf-8"))
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == step_name:
                return step["run"]
    raise AssertionError(f"{workflow}: {step_name} step 없음")


def _run(script: str, cwd: Path):
    # macOS 기본 bash 3.2 + BSD grep 으로도 같은 결과여야 한다
    bash = "/bin/bash" if Path("/bin/bash").exists() else "bash"
    env = {"PATH": os.environ.get("PATH", ""), "APP_ROOT": "app"}
    return subprocess.run([bash, "-e", "-c", script], cwd=cwd, env=env, capture_output=True, text=True)


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_missing_export_options_explains_how_to_create_it(workflow, tmp_path):
    (tmp_path / "ios").mkdir()
    result = _run(_step_script(workflow, "Verify ExportOptions.plist"), tmp_path)
    assert result.returncode == 1
    assert "::error title=Missing ios/ExportOptions.plist::" in result.stdout
    assert "app/ios/ExportOptions.plist" in result.stdout
    assert WIZARD in result.stdout and "testflight-wizard.html" in result.stdout


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_present_export_options_passes(workflow, tmp_path):
    (tmp_path / "ios").mkdir()
    (tmp_path / "ios/ExportOptions.plist").write_text("<plist/>")
    assert _run(_step_script(workflow, "Verify ExportOptions.plist"), tmp_path).returncode == 0


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_missing_fastfile_explains_how_to_create_it(workflow, tmp_path):
    result = _run(_step_script(workflow, "Verify Fastfile exists"), tmp_path)
    assert result.returncode == 1
    assert "::error title=Missing ios/fastlane/Fastfile::" in result.stdout
    assert WIZARD in result.stdout


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("body,has_lane", [
    ("platform :ios do\n  lane :deploy do\n  end\nend\n", True),
    ("  lane(:deploy) do\n", True),
    ("  lane :deploy\n", True),
    ("  lane :deploy_beta do\n  lane :upload_testflight do\n", False),
    ("  # lane :deploy do\n", False),
])
def test_fastfile_without_deploy_lane_only_warns(workflow, body, has_lane, tmp_path):
    # 직접 만든 Fastfile 을 오탐으로 막지 않도록 경고만 하고 통과한다
    (tmp_path / "ios/fastlane").mkdir(parents=True)
    (tmp_path / "ios/fastlane/Fastfile").write_text(body)
    result = _run(_step_script(workflow, "Verify Fastfile exists"), tmp_path)
    assert result.returncode == 0, result.stderr
    assert ("::warning title=Fastfile has no deploy lane::" in result.stdout) is (not has_lane)
