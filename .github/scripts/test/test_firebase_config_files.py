"""Firebase 설정 파일 복원과 누락 진단 (#785).

실사고 계열: Android 배포가 Secret 이 없어도 google-services.json 을 빈 줄로 덮어썼고,
iOS 는 GoogleService-Info.plist 를 복원하는 단계가 아예 없어 원인 모를 빌드 실패로 끝났다.
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import firebase_config_files as fc  # noqa: E402

SCRIPT = SCRIPTS / "firebase_config_files.py"
FLUTTER = SCRIPTS.parents[1] / ".github" / "workflows" / "project-types" / "flutter"
PLIST = '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict/></plist>\n'


def _cli(app_root, platform, secret):
    env = {"PATH": "/usr/bin:/bin", fc.PLATFORMS[platform][0]: secret}
    run = subprocess.run([sys.executable, str(SCRIPT), "restore", "--platform", platform, "--app-root", str(app_root)],
                         capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    lines = run.stdout.strip().splitlines()
    return lines[0], json.loads(lines[-1])


def test_Secret_이_있으면_파일로_쓰고_내용은_출력하지_않는다(tmp_path):
    first, result = _cli(tmp_path, "android", '{"project_info": {"project_id": "secret-id"}}')
    assert result["action"] == "written"
    assert json.loads((tmp_path / "android/app/google-services.json").read_text())["project_info"]
    assert "secret-id" not in first and "secret-id" not in json.dumps(result)


@pytest.mark.parametrize("secret", [PLIST, base64.b64encode(PLIST.encode()).decode()], ids=["raw", "base64"])
def test_iOS_plist_는_원문과_base64_를_모두_받는다(tmp_path, secret):
    _cli(tmp_path, "ios", secret)
    assert (tmp_path / "ios/Runner/GoogleService-Info.plist").read_text() == PLIST


def test_Secret_이_없으면_커밋된_파일을_덮어쓰지_않는다(tmp_path):
    committed = tmp_path / "android/app/google-services.json"
    committed.parent.mkdir(parents=True)
    committed.write_text('{"committed": true}\n')
    first, result = _cli(tmp_path, "android", "")
    assert result["action"] == "skipped" and committed.read_text() == '{"committed": true}\n'
    assert not first.startswith("::error")


def test_Secret_도_파일도_없고_필요도_없으면_조용히_건너뛴다(tmp_path):
    first, result = _cli(tmp_path, "ios", "")
    assert result["action"] == "skipped" and not result["referenced_by"]
    assert not first.startswith("::")


@pytest.mark.parametrize("platform,referencing,content", [
    ("android", "android/app/build.gradle.kts", 'plugins { id("com.google.gms.google-services") }\n'),
    ("android", "android/settings.gradle", 'id "com.google.gms.google-services" version "4.4.2" apply false\n'),
    ("ios", "ios/Runner.xcodeproj/project.pbxproj", "/* GoogleService-Info.plist in Resources */\n"),
])
def test_프로젝트가_요구하는데_없으면_원인과_Secret_이름을_error_로_남긴다(tmp_path, platform, referencing, content):
    (tmp_path / referencing).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / referencing).write_text(content)
    first, result = _cli(tmp_path, platform, "")
    assert result["referenced_by"] == [referencing]
    assert first.startswith("::error title=Missing Firebase config::")
    assert fc.PLATFORMS[platform][0] in first and fc.PLATFORMS[platform][1] in first


def _restore_steps(name):
    doc = yaml.safe_load((FLUTTER / name).read_text(encoding="utf-8"))
    return [(job_id, s) for job_id, job in doc["jobs"].items() for s in job.get("steps", [])
            if "firebase_config_files.py\" restore" in str(s.get("run", ""))]


@pytest.mark.parametrize("name,platforms", [
    ("PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml", {"android"}),
    ("PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml", {"android"}),
    ("PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml", {"android"}),
    ("PROJECT-FLUTTER-ANDROID-TEST-APK.yaml", {"android"}),
    ("PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml", {"ios"}),
    ("PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml", {"ios"}),
    ("PROJECT-FLUTTER-CI.yaml", {"android", "ios"}),
])
def test_Flutter_빌드_워크플로우는_같은_스크립트로_복원한다(name, platforms):
    steps = _restore_steps(name)
    assert {s["run"].split("--platform ")[1].split()[0] for _job, s in steps} == platforms
    for _job, step in steps:
        platform = step["run"].split("--platform ")[1].split()[0]
        secret = fc.PLATFORMS[platform][0]
        assert step["env"][secret] == "${{ secrets.%s }}" % secret
    # 직접 printf 로 쓰던 옛 방식이 남아 있으면 Secret 없을 때 빈 파일로 덮어쓴다
    text = (FLUTTER / name).read_text(encoding="utf-8")
    assert "> android/app/google-services.json" not in text


@pytest.mark.parametrize("name,job", [
    ("PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml", "build-upload-ios"),
    ("PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml", "build-upload-ios-test"),
])
def test_iOS_plist_복원은_env_보장_바로_뒤_Flutter_설정_앞이다(name, job):
    # OAuth 마법사(#156)가 안내하는 자리·Secret 이름과 같아야 사용자가 중복 스텝을 만들지 않는다
    doc = yaml.safe_load((FLUTTER / name).read_text(encoding="utf-8"))
    names = [s.get("name") for s in doc["jobs"][job]["steps"]]
    index = names.index("Create GoogleService-Info.plist")
    assert names[index - 1] == "Ensure .env file exists"
    assert names[index + 1] == "Set up Flutter"
    step = doc["jobs"][job]["steps"][index]
    assert step["env"] == {"GOOGLE_SERVICE_INFO_PLIST": "${{ secrets.GOOGLE_SERVICE_INFO_PLIST }}"}
