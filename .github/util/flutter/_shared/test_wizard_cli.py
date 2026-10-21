#!/usr/bin/env python3
"""Flutter 마법사 CLI 계약 테스트 (testflight·playstore·firebase·oauth).

무엇을 지키려는 테스트인가
--------------------------
1. 명명 플래그와 구 위치인자가 **둘 다** 동작해야 한다.
   (마법사 HTML이 이미 배포한 명령어가 위치인자 형식이라 끊으면 안 된다)
2. `--dry-run`은 디스크를 한 바이트도 바꾸지 않아야 한다.
   실행 흐름은 실제 실행과 같아야 한다(종료 코드 동일).
   → 과거 "쓰기만 건너뛰기" 방식은 뒷 단계가 낡은 내용을 읽어
     거짓 실패를 냈다. 오버레이 도입 후의 회귀를 막는다.
3. `--no-backup`은 .bak 파일을 만들지 않아야 한다.

실행:
    python3 -m pytest .github/util/flutter/_shared/test_wizard_cli.py -q
    python3 .github/util/flutter/_shared/test_wizard_cli.py     # pytest 없이도 동작
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

FLUTTER_DIR = Path(__file__).resolve().parent.parent

TF = FLUTTER_DIR / "testflight-wizard" / "testflight-wizard.py"
PS = FLUTTER_DIR / "playstore-wizard" / "playstore-wizard.py"
FB = FLUTTER_DIR / "firebase-wizard" / "firebase-wizard.py"
OA = FLUTTER_DIR / "oauth-wizard" / "oauth-wizard.py"

TF_ORDER = ("project-path", "bundle-id", "team-id", "profile-name", "uses-encryption")
PS_ORDER = ("project-path", "application-id", "key-alias", "store-password", "key-password",
            "validity-days", "cert-cn", "cert-o", "cert-l", "cert-c")


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"wz_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _flutter_ios_project(root: Path) -> None:
    (root / "pubspec.yaml").write_text("name: demo\n", encoding="utf-8")
    xcode = root / "ios" / "Runner.xcodeproj"
    xcode.mkdir(parents=True)
    (xcode / "project.pbxproj").write_text(
        "{\n\tbuildSettings = {\n\t\tPRODUCT_BUNDLE_IDENTIFIER = com.old.app;\n"
        "\t\tCODE_SIGN_STYLE = Automatic;\n\t};\n}\n", encoding="utf-8")
    runner = root / "ios" / "Runner"
    runner.mkdir(parents=True)
    (runner / "Info.plist").write_text("<plist><dict>\n</dict></plist>\n", encoding="utf-8")


def _flutter_android_project(root: Path) -> None:
    (root / "pubspec.yaml").write_text("name: demo\n", encoding="utf-8")
    app = root / "android" / "app"
    app.mkdir(parents=True)
    (app / "build.gradle.kts").write_text(
        'android {\n    namespace = "com.old.app"\n    defaultConfig {\n'
        '        applicationId = "com.old.app"\n    }\n}\n', encoding="utf-8")
    (root / ".gitignore").write_text("", encoding="utf-8")


def _run(script: Path, args: list[str]) -> int:
    return subprocess.run([sys.executable, str(script), "setup", *args],
                          capture_output=True, text=True).returncode


# ── 1. 인자 정규화: 명명 플래그 ↔ 위치인자 ──────────────────────────

def test_normalize_positional_still_works():
    tf = _load(TF)
    got, _ = tf.normalize_params(["/p", "com.a.b", "ABC123", "My Profile"], TF_ORDER)
    assert got == ["/p", "com.a.b", "ABC123", "My Profile"]


def test_normalize_named_flags():
    tf = _load(TF)
    got, _ = tf.normalize_params(
        ["--project-path", "/p", "--bundle-id", "com.a.b",
         "--team-id", "ABC123", "--profile-name", "My Profile"], TF_ORDER)
    assert got[:4] == ["/p", "com.a.b", "ABC123", "My Profile"]


def test_normalize_named_flags_order_independent():
    """--key=value 형식 + 순서를 뒤섞어도 같은 결과여야 한다"""
    tf = _load(TF)
    got, _ = tf.normalize_params(
        ["--team-id=ABC123", "--project-path=/p",
         "--profile-name=My Profile", "--bundle-id=com.a.b"], TF_ORDER)
    assert got[:4] == ["/p", "com.a.b", "ABC123", "My Profile"]


def test_normalize_playstore_ten_positionals():
    ps = _load(PS)
    argv = ["/p", "com.a.b", "key", "sp", "kp", "10000", "cn", "o", "l", "KR"]
    got, _ = ps.normalize_params(list(argv), PS_ORDER)
    assert got == argv


def test_common_boolean_flags():
    tf = _load(TF)
    _, opts = tf.normalize_params(
        ["--project-path", "/p", "--bundle-id", "b", "--team-id", "t",
         "--profile-name", "n", "--dry-run", "--non-interactive", "--no-backup"], TF_ORDER)
    assert opts == {"dry_run": True, "non_interactive": True, "backup": False}


def test_unknown_flag_is_rejected():
    tf = _load(TF)
    try:
        tf.normalize_params(["--nope", "x"], TF_ORDER)
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("알 수 없는 옵션인데 종료하지 않았습니다")


# ── 2. dry-run: 디스크 무변경 + 실제 실행과 같은 흐름 ────────────────

def test_testflight_dry_run_changes_nothing_and_matches_real_run():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        pa, pb = Path(a), Path(b)
        _flutter_ios_project(pa)
        _flutter_ios_project(pb)
        before = _snapshot(pa)

        common = ["--bundle-id", "com.demo.app", "--team-id", "ABCDE12345",
                  "--profile-name", "Demo"]
        rc_dry = _run(TF, ["--project-path", str(pa), *common, "--dry-run"])
        rc_real = _run(TF, ["--project-path", str(pb), *common])

        assert _snapshot(pa) == before, "dry-run이 파일을 변경했습니다"
        assert rc_dry == rc_real, f"dry-run({rc_dry}) 과 실제({rc_real}) 종료 코드가 다릅니다"
        assert (pb / "ios" / "ExportOptions.plist").exists(), "실제 실행이 산출물을 만들지 못했습니다"


def test_playstore_dry_run_changes_nothing_and_matches_real_run():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        pa, pb = Path(a), Path(b)
        _flutter_android_project(pa)
        _flutter_android_project(pb)
        before = _snapshot(pa)

        common = ["--application-id", "com.demo.app", "--key-alias", "k",
                  "--store-password", "pw123456", "--key-password", "pw123456",
                  "--validity-days", "10000", "--cert-cn", "D", "--cert-o", "O",
                  "--cert-l", "S", "--cert-c", "KR"]
        rc_dry = _run(PS, ["--project-path", str(pa), *common, "--dry-run"])
        rc_real = _run(PS, ["--project-path", str(pb), *common])

        assert _snapshot(pa) == before, "dry-run이 파일을 변경했습니다"
        assert rc_dry == rc_real, f"dry-run({rc_dry}) 과 실제({rc_real}) 종료 코드가 다릅니다"


def test_playstore_dry_run_does_not_create_keystore():
    """keytool은 실제 파일을 만드는 외부 명령 — dry-run에서 실행되면 안 된다"""
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_android_project(pa)
        _run(PS, ["--project-path", str(pa), "--application-id", "com.demo.app",
                  "--key-alias", "k", "--store-password", "pw123456",
                  "--key-password", "pw123456", "--validity-days", "10000",
                  "--cert-cn", "D", "--cert-o", "O", "--cert-l", "S",
                  "--cert-c", "KR", "--dry-run"])
        assert not (pa / "android" / "app" / "keystore" / "key.jks").exists()


# ── 3. --no-backup ────────────────────────────────────────────────

def test_testflight_no_backup_skips_bak_files():
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_ios_project(pa)
        _run(TF, ["--project-path", str(pa), "--bundle-id", "com.demo.app",
                  "--team-id", "ABCDE12345", "--profile-name", "Demo", "--no-backup"])
        baks = list(pa.rglob("*.bak"))
        assert not baks, f"--no-backup인데 백업이 생겼습니다: {baks}"


# ── 3.5 store-deploy.json 기록 (#767) ─────────────────────────────

import json  # noqa: E402

PS_BASE = ["--application-id", "com.demo.app", "--key-alias", "k",
           "--store-password", "pw123456", "--key-password", "pw123456",
           "--validity-days", "10000", "--cert-cn", "D", "--cert-o", "O",
           "--cert-l", "S", "--cert-c", "KR"]


def _run_out(script: Path, args: list[str]):
    r = subprocess.run([sys.executable, str(script), "setup", *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_playstore_records_deploy_mode_in_store_deploy_json():
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_android_project(pa)
        rc, _ = _run_out(PS, ["--project-path", str(pa), *PS_BASE,
                              "--deploy-mode", "store_prepare", "--production-rollout", "0.1"])
        assert rc == 0
        data = json.loads((pa / ".github" / "config" / "store-deploy.json").read_text(encoding="utf-8"))
        assert data["android"] == {"deploy_mode": "store_prepare", "production_rollout": "0.1"}


def test_playstore_deploy_config_keeps_other_sections():
    """이미 있는 ios 섹션과 사용자 키를 지우지 않고 android 만 갱신한다"""
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_android_project(pa)
        cfg = pa / ".github" / "config"
        cfg.mkdir(parents=True)
        (cfg / "store-deploy.json").write_text(
            json.dumps({"_comment": "mine", "ios": {"deploy_mode": "store_only"}}), encoding="utf-8")
        rc, _ = _run_out(PS, ["--project-path", str(pa), *PS_BASE, "--deploy-mode", "store_submit"])
        assert rc == 0
        data = json.loads((cfg / "store-deploy.json").read_text(encoding="utf-8"))
        assert data["_comment"] == "mine" and data["ios"] == {"deploy_mode": "store_only"}
        assert data["android"] == {"deploy_mode": "store_submit"}


def test_playstore_without_deploy_flags_creates_no_config():
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_android_project(pa)
        rc, _ = _run_out(PS, ["--project-path", str(pa), *PS_BASE])
        assert rc == 0
        assert not (pa / ".github" / "config" / "store-deploy.json").exists()


def test_playstore_deploy_config_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_android_project(pa)
        before = _snapshot(pa)
        rc, _ = _run_out(PS, ["--project-path", str(pa), *PS_BASE, "--deploy-mode", "store_prepare", "--dry-run"])
        assert rc == 0
        assert _snapshot(pa) == before, "dry-run 이 store-deploy.json 이나 다른 파일을 만들었다"


def test_playstore_invalid_deploy_values_fail_before_any_side_effect():
    """오타를 조용히 넘기면 설정이 먹었다고 믿은 채 다른 모드로 배포된다 — 키스토어를 만들기 전에 멈춘다"""
    for bad in (["--deploy-mode", "store_submt"], ["--production-rollout", "1.5"],
                ["--production-rollout", "0"], ["--production-rollout", "abc"]):
        with tempfile.TemporaryDirectory() as a:
            pa = Path(a)
            _flutter_android_project(pa)
            before = _snapshot(pa)
            rc, out = _run_out(PS, ["--project-path", str(pa), *PS_BASE, *bad])
            assert rc != 0, f"{bad} 가 통과했다"
            assert _snapshot(pa) == before, f"{bad}: 실패했는데 파일이 만들어졌다"

# ── 4. 마법사 CLI 표면 동일성 ─────────────────────────────────────

def test_all_wizards_accept_common_flags():
    """모든 마법사가 --dry-run / --non-interactive / --no-backup 을 인식해야 한다"""
    for script in (TF, PS, FB, OA):
        text = script.read_text(encoding="utf-8")
        for flag in ("--dry-run", "--non-interactive", "--no-backup"):
            assert flag in text, f"{script.name}: {flag} 미지원"


# ── 5. oauth: 네이티브 설정 패치 (#156) ──────────────────────────────

KAKAO_KEY = "0123456789abcdef0123456789abcdef"
OTHER_KAKAO_KEY = "fedcba9876543210fedcba9876543210"
IOS_CLIENT_ID = "1234-abc.apps.googleusercontent.com"
WEB_CLIENT_ID = "1234-web.apps.googleusercontent.com"
OA_ALL = ["--kakao-native-app-key", KAKAO_KEY, "--google-ios-client-id", IOS_CLIENT_ID,
          "--google-server-client-id", WEB_CLIENT_ID, "--update-gitignore", "--firebase-files",
          "--non-interactive"]

FLUTTER_MANIFEST = """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application android:label="demo">
        <activity android:name=".MainActivity" android:exported="true">
        </activity>
    </application>
</manifest>
"""
FLUTTER_INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDisplayName</key>
	<string>Demo</string>
	<key>CFBundleURLTypes</key>
	<array>
		<dict>
			<key>CFBundleURLSchemes</key>
			<array>
				<string>myapp</string>
			</array>
		</dict>
	</array>
</dict>
</plist>
"""


def _flutter_oauth_project(root: Path) -> None:
    (root / "pubspec.yaml").write_text("name: demo\n", encoding="utf-8")
    manifest = root / "android" / "app" / "src" / "main"
    manifest.mkdir(parents=True)
    (manifest / "AndroidManifest.xml").write_text(FLUTTER_MANIFEST, encoding="utf-8")
    (root / "android" / "app" / "build.gradle.kts").write_text(
        'android {\n    defaultConfig {\n        applicationId = "com.demo.app"\n    }\n}\n', encoding="utf-8")
    runner = root / "ios" / "Runner"
    runner.mkdir(parents=True)
    (runner / "Info.plist").write_text(FLUTTER_INFO_PLIST, encoding="utf-8")
    xcode = root / "ios" / "Runner.xcodeproj"
    xcode.mkdir(parents=True)
    (xcode / "project.pbxproj").write_text(
        "PRODUCT_BUNDLE_IDENTIFIER = com.demo.app;\nPRODUCT_BUNDLE_IDENTIFIER = com.demo.app.RunnerTests;\n",
        encoding="utf-8")
    (root / ".gitignore").write_text("build/\n", encoding="utf-8")


def _run_oauth(command: str, args: list[str]):
    r = subprocess.run([sys.executable, str(OA), command, *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def _read_plist(root: Path) -> dict:
    import plistlib
    return plistlib.loads((root / "ios" / "Runner" / "Info.plist").read_bytes())


def _url_schemes(plist: dict) -> list[str]:
    return [s for t in plist.get("CFBundleURLTypes", []) for s in t.get("CFBundleURLSchemes", [])]


def _change_plan(output: str, root: Path) -> list[str]:
    return [line.replace(str(root), "") for line in output.splitlines()
            if line.startswith(("[changed]", "[unchanged]"))]


def test_oauth_fresh_patch_adds_kakao_and_google_entries():
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_oauth_project(pa)
        rc, out = _run_oauth("setup", ["--project-path", str(pa), *OA_ALL])
        assert rc == 0, out
        manifest = (pa / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        assert "com.kakao.sdk.flutter.auth.AuthCodeHandlerActivity" in manifest
        assert f'android:scheme="kakao{KAKAO_KEY}" android:host="oauth"' in manifest
        assert manifest.index("AuthCodeHandlerActivity") < manifest.index("</application>")
        plist = _read_plist(pa)
        # 기존 URL scheme(myapp)은 남기고 kakao·google scheme 을 더한다
        assert _url_schemes(plist) == ["myapp", f"kakao{KAKAO_KEY}", "com.googleusercontent.apps.1234-abc"]
        assert plist["LSApplicationQueriesSchemes"] == ["kakaokompassauth", "kakaolink"]
        assert plist["GIDClientID"] == IOS_CLIENT_ID and plist["GIDServerClientID"] == WEB_CLIENT_ID
        gitignore = (pa / ".gitignore").read_text(encoding="utf-8")
        assert gitignore.startswith("build/\n")
        assert "android/app/google-services.json" in gitignore and "oauth-secrets-*.json" in gitignore


def test_oauth_rerun_is_idempotent():
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_oauth_project(pa)
        _run_oauth("setup", ["--project-path", str(pa), *OA_ALL, "--no-backup"])
        after_first = _snapshot(pa)
        rc, out = _run_oauth("setup", ["--project-path", str(pa), *OA_ALL])
        assert rc == 0, out
        assert _snapshot(pa) == after_first, "두 번째 실행이 파일을 바꿨거나 백업을 만들었다"
        assert "Nothing to change" in out


def test_oauth_dry_run_writes_nothing_and_matches_real_run():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        pa, pb = Path(a), Path(b)
        _flutter_oauth_project(pa)
        _flutter_oauth_project(pb)
        before = _snapshot(pa)
        rc_dry, out_dry = _run_oauth("setup", ["--project-path", str(pa), *OA_ALL, "--dry-run"])
        rc_real, out_real = _run_oauth("setup", ["--project-path", str(pb), *OA_ALL])
        assert _snapshot(pa) == before, "dry-run이 파일을 변경했습니다"
        assert rc_dry == rc_real == 0
        # 같은 변경 계획을 출력한다 (경로만 다름)
        assert _change_plan(out_dry, pa) and _change_plan(out_dry, pa) == _change_plan(out_real, pb)


def test_oauth_no_backup_skips_bak_files():
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_oauth_project(pa)
        _run_oauth("setup", ["--project-path", str(pa), *OA_ALL, "--no-backup"])
        assert not list(pa.rglob("*.bak"))


def test_oauth_updates_changed_kakao_key_instead_of_duplicating():
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_oauth_project(pa)
        _run_oauth("setup", ["--project-path", str(pa), "--kakao-native-app-key", OTHER_KAKAO_KEY, "--non-interactive"])
        rc, out = _run_oauth("setup", ["--project-path", str(pa), "--kakao-native-app-key", KAKAO_KEY,
                                       "--non-interactive", "--no-backup"])
        assert rc == 0, out
        manifest = (pa / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        assert manifest.count("AuthCodeHandlerActivity") == 1
        assert OTHER_KAKAO_KEY not in manifest and KAKAO_KEY in manifest
        assert _url_schemes(_read_plist(pa)) == ["myapp", f"kakao{KAKAO_KEY}"]


def test_oauth_invalid_input_changes_nothing():
    """REST API 키처럼 잘못된 값이면 파일을 건드리기 전에 멈춘다"""
    for bad in (["--kakao-native-app-key", "not-a-key"], ["--google-ios-client-id", "1234.apps.example.com"],
                ["--google-server-client-id", WEB_CLIENT_ID]):
        with tempfile.TemporaryDirectory() as a:
            pa = Path(a)
            _flutter_oauth_project(pa)
            before = _snapshot(pa)
            rc, _ = _run_oauth("setup", ["--project-path", str(pa), *bad, "--non-interactive"])
            assert rc != 0, f"{bad} 가 통과했다"
            assert _snapshot(pa) == before, f"{bad}: 실패했는데 파일이 바뀌었다"


def test_oauth_missing_info_plist_changes_nothing():
    """한 파일이라도 없으면 다른 파일도 바꾸지 않는다 (계획 먼저, 쓰기는 나중)"""
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_oauth_project(pa)
        (pa / "ios" / "Runner" / "Info.plist").unlink()
        before = _snapshot(pa)
        rc, out = _run_oauth("setup", ["--project-path", str(pa), *OA_ALL])
        assert rc == 1 and "Info.plist not found" in out
        assert _snapshot(pa) == before


def test_oauth_detect_reads_app_ids_without_writing():
    with tempfile.TemporaryDirectory() as a:
        pa = Path(a)
        _flutter_oauth_project(pa)
        before = _snapshot(pa)
        rc, out = _run_oauth("detect", ["--project-path", str(pa)])
        assert rc == 0
        data = json.loads(out)
        assert data["applicationId"]["value"] == "com.demo.app"
        assert data["bundleId"]["value"] == "com.demo.app"
        assert _snapshot(pa) == before


def test_oauth_key_hash_matches_openssl_formula():
    """SHA-1(16진) > base64 — sha1("") 의 알려진 값으로 확인"""
    rc, out = _run_oauth("key-hash", ["--sha1", "DA:39:A3:EE:5E:6B:4B:0D:32:55:BF:EF:95:60:18:90:AF:D8:07:09"])
    assert rc == 0
    assert json.loads(out)["kakaoKeyHash"] == "2jmj7l5rSw0yVb/vlWAYkK/YBwk="


def _main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅ {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ❌ {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
