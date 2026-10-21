"""워크플로우 고정 Flutter·Java 버전 <-> 레포 요구 대조 (#758).

고정값이 낡아 의존성 업데이트 뒤 빌드가 깨지는 사고를 미리 경고한다. 경고만 하고 빌드는 계속한다.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import toolchain_versions as tv  # noqa: E402

SCRIPT = SCRIPTS / "toolchain_versions.py"


@pytest.mark.parametrize("version,constraint,expected", [
    ("3.38.9", ">=3.22.0", True),
    ("3.38.9", ">=3.40.0", False),
    ("3.38.9", ">=3.10.0 <4.0.0", True),
    ("3.38.9", "^3.38.0", True),
    ("3.38.9", "^3.39.0", False),
    ("3.38.9", "3.38.9", True),
    ("3.38.9", "'3.35.5'", False),
    ("3.38.9", "any", True),
    ("3.38.9", ">3.38.9", False),
    ("0.5.0", "^0.4.0", False),
])
def test_pub_제약을_해석한다(version, constraint, expected):
    assert tv.satisfies(tv.parse_version(version), constraint) is expected


def test_해석할_수_없는_제약은_판정하지_않는다():
    assert tv.satisfies((3, 38, 9), ">=abc") is None


def _repo(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_모두_맞으면_경고가_없다(tmp_path):
    repo = _repo(tmp_path, {
        ".fvmrc": json.dumps({"flutter": "3.38.9"}),
        "pubspec.yaml": "name: app\nenvironment:\n  sdk: '>=3.5.0 <4.0.0'\n  flutter: \">=3.22.0\"\n",
        ".java-version": "17\n",
        "android/app/build.gradle.kts": "kotlin {\n    jvmToolchain(17)\n}\n",
    })
    result = tv.check(repo, "3.38.9", "17")
    assert result["findings"] == []
    assert set(result["checked"]) == {".fvmrc", "pubspec.yaml environment.flutter", ".java-version",
                                      "android/app/build.gradle.kts toolchain"}


def test_어긋나면_근거와_레포_변수_안내를_담아_경고한다(tmp_path):
    repo = _repo(tmp_path, {
        ".flutter-version": "3.41.0\n",
        "pubspec.yaml": "environment:\n  sdk: ^3.9.0\n  flutter: '>=3.40.0'  # 새 SDK 필요\n",
        ".tool-versions": "java temurin-21.0.2\nnodejs 20\n",
        "android/build.gradle": "java { toolchain { languageVersion = JavaLanguageVersion.of(21) } }\n",
    })
    result = tv.check(repo, "3.38.9", "17")
    sources = sorted(f["source"] for f in result["findings"])
    assert sources == [".flutter-version", ".tool-versions", "android/build.gradle toolchain",
                       "pubspec.yaml environment.flutter"]
    flutter_msgs = [f["message"] for f in result["findings"] if f["tool"] == "flutter"]
    assert all("FLUTTER_VERSION 3.38.9" in m and "repository variable FLUTTER_VERSION" in m for m in flutter_msgs)
    java_msgs = [f["message"] for f in result["findings"] if f["tool"] == "java"]
    assert all("JAVA_VERSION 17" in m and "repository variable JAVA_VERSION" in m for m in java_msgs)


def test_채널_이름과_치환_전_자리표시자는_대조하지_않는다(tmp_path):
    repo = _repo(tmp_path, {".fvmrc": json.dumps({"flutter": "stable"}), ".java-version": "21"})
    result = tv.check(repo, "3.38.9", "__JAVA_VERSION__")
    assert result["findings"] == [] and result["checked"] == []


def test_fvm_2_설정도_읽는다(tmp_path):
    repo = _repo(tmp_path, {".fvm/fvm_config.json": json.dumps({"flutterSdkVersion": "3.35.5"})})
    assert [f["source"] for f in tv.check(repo, "3.38.9", "")["findings"]] == [".fvm/fvm_config.json"]


def test_CLI_는_경고만_내고_항상_0_으로_끝나며_요약에_남긴다(tmp_path):
    repo = _repo(tmp_path / "app", {".flutter-version": "3.41.0"})
    summary = tmp_path / "summary.md"
    run = subprocess.run([sys.executable, str(SCRIPT), "check", "--app-root", str(repo)],
                         capture_output=True, text=True,
                         env={"FLUTTER_VERSION": "3.38.9", "JAVA_VERSION": "17", "GITHUB_STEP_SUMMARY": str(summary),
                              "PATH": "/usr/bin:/bin"})
    assert run.returncode == 0
    assert run.stdout.startswith("::warning title=Toolchain version mismatch (flutter)::.flutter-version asks for Flutter 3.41.0")
    assert json.loads(run.stdout.strip().splitlines()[-1])["findings"]
    assert "### Toolchain version mismatch" in summary.read_text(encoding="utf-8")


def test_Flutter_워크플로우는_레포_변수로_버전을_덮어쓸_수_있다():
    # 템플릿 업데이트가 워크플로우 env 를 덮어써도 레포 변수는 남는다 (vars.XCODE_VERSION 과 같은 방식)
    flutter = SCRIPTS.parents[1] / ".github" / "workflows" / "project-types" / "flutter"
    for wf in sorted(flutter.glob("*.yaml")):
        text = wf.read_text(encoding="utf-8")
        assert "flutter-version: ${{ env.FLUTTER_VERSION }}" not in text, wf.name
        assert "java-version: ${{ env.JAVA_VERSION }}" not in text, wf.name


def test_Flutter_CI_가_버전_대조를_경고로_돌린다():
    import yaml
    ci = yaml.safe_load((SCRIPTS.parents[1] / ".github" / "workflows" / "project-types" / "flutter"
                         / "PROJECT-FLUTTER-CI.yaml").read_text(encoding="utf-8"))
    steps = [s for job in ci["jobs"].values() for s in job.get("steps", [])
             if re.search(r"toolchain_versions\.py\"? check", str(s.get("run", "")))]
    assert len(steps) == 1
    step = steps[0]
    assert step.get("continue-on-error") is True
    assert step["env"]["FLUTTER_VERSION"] == "${{ vars.FLUTTER_VERSION || env.FLUTTER_VERSION }}"
    assert step["env"]["JAVA_VERSION"] == "${{ vars.JAVA_VERSION || env.JAVA_VERSION }}"
