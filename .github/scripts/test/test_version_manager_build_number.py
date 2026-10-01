"""react-native 빌드 번호(versionCode·CFBundleVersion) 동기화 회귀 테스트 (#721)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_version_manager_fixes import run_vm, write  # noqa: E402

YML_RN = 'version: "1.2.3"\nversion_code: 5\nproject_types: ["react-native"]\n'
PLIST = ("<dict>\n<key>CFBundleShortVersionString</key>\n<string>%s</string>\n"
         "<key>CFBundleVersion</key>\n<string>%s</string>\n</dict>\n")
GRADLE = "android {\n    defaultConfig {\n        versionCode %s\n        versionName \"%s\"\n    }\n}\n"


def rd(p):
    return Path(p).read_bytes().decode("utf-8")


def setup(tmp_path, code="1", ver="1.2.3"):
    write(tmp_path / "version.yml", YML_RN)
    write(tmp_path / "ios/App/Info.plist", PLIST % (ver, code))
    write(tmp_path / "android/app/build.gradle", GRADLE % (code, ver))


def test_increment_syncs_build_number(tmp_path):
    setup(tmp_path)
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert rd(tmp_path / "ios/App/Info.plist") == PLIST % ("1.2.4", "6")
    assert rd(tmp_path / "android/app/build.gradle") == GRADLE % ("6", "1.2.4")


def test_increment_code_syncs_build_number(tmp_path):
    setup(tmp_path)
    rc, out, err = run_vm(tmp_path, "increment-code")
    assert rc == 0, err
    assert out.strip() == "6"
    assert rd(tmp_path / "ios/App/Info.plist") == PLIST % ("1.2.3", "6")
    assert rd(tmp_path / "android/app/build.gradle") == GRADLE % ("6", "1.2.3")


def test_set_syncs_current_code_without_incrementing(tmp_path):
    setup(tmp_path)
    rc, out, err = run_vm(tmp_path, "set", "2.0.0")
    assert rc == 0, err
    assert "version_code: 5" in rd(tmp_path / "version.yml")
    assert rd(tmp_path / "ios/App/Info.plist") == PLIST % ("2.0.0", "5")
    assert rd(tmp_path / "android/app/build.gradle") == GRADLE % ("5", "2.0.0")


def test_idempotent_when_already_same(tmp_path):
    setup(tmp_path, code="5")
    plist, gradle = tmp_path / "ios/App/Info.plist", tmp_path / "android/app/build.gradle"
    import os
    for f in (plist, gradle):
        os.utime(f, (1_000_000, 1_000_000))
    rc, out, err = run_vm(tmp_path, "set", "1.2.3")
    assert rc == 0, err
    assert plist.stat().st_mtime == 1_000_000 and gradle.stat().st_mtime == 1_000_000


def test_pods_plist_excluded(tmp_path):
    setup(tmp_path)
    write(tmp_path / "ios/Pods/X/Info.plist", PLIST % ("9.0.0", "77"))
    rc, out, err = run_vm(tmp_path, "increment")
    assert rc == 0, err
    assert rd(tmp_path / "ios/Pods/X/Info.plist") == PLIST % ("9.0.0", "77")


def test_crlf_and_indent_preserved(tmp_path):
    write(tmp_path / "version.yml", YML_RN)
    write(tmp_path / "android/app/build.gradle", (GRADLE % ("1", "1.2.3")).replace("\n", "\r\n"))
    write(tmp_path / "ios/App/Info.plist", (PLIST % ("1.2.3", "1")).replace("\n", "\r\n"))
    rc, out, err = run_vm(tmp_path, "increment-code")
    assert rc == 0, err
    assert rd(tmp_path / "android/app/build.gradle") == (GRADLE % ("6", "1.2.3")).replace("\n", "\r\n")
    assert rd(tmp_path / "ios/App/Info.plist") == (PLIST % ("1.2.3", "6")).replace("\n", "\r\n")


def test_variable_or_missing_patterns_warn_only(tmp_path):
    write(tmp_path / "version.yml", YML_RN)
    gradle = "defaultConfig {\n  versionCode rootProject.ext.versionCode\n}\n"
    plist = "<dict>\n<key>CFBundleShortVersionString</key>\n<string>1.2.3</string>\n<key>CFBundleVersion</key>\n<string>$(CURRENT_PROJECT_VERSION)</string>\n</dict>\n"
    write(tmp_path / "android/app/build.gradle", gradle)
    write(tmp_path / "ios/App/Info.plist", plist)
    rc, out, err = run_vm(tmp_path, "increment-code")
    assert rc == 0, err
    assert rd(tmp_path / "android/app/build.gradle") == gradle
    assert rd(tmp_path / "ios/App/Info.plist") == plist
    assert "경고" in err or "⚠️" in err


def test_missing_files_do_not_fail(tmp_path):
    write(tmp_path / "version.yml", YML_RN)
    rc, out, err = run_vm(tmp_path, "increment-code")
    assert rc == 0, err


def test_non_react_native_untouched(tmp_path):
    # basic·expo 타입은 이번 범위 밖이라 빌드 번호 파일을 건드리지 않는다
    write(tmp_path / "version.yml", 'version: "1.2.3"\nversion_code: 5\nproject_types: ["spring"]\n')
    write(tmp_path / "android/app/build.gradle", GRADLE % ("1", "1.2.3"))
    rc, out, err = run_vm(tmp_path, "increment-code")
    assert rc == 0, err
    assert rd(tmp_path / "android/app/build.gradle") == GRADLE % ("1", "1.2.3")
