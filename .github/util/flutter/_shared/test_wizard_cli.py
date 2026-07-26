#!/usr/bin/env python3
"""Flutter 마법사 3종 CLI 계약 테스트.

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


# ── 4. 3종 CLI 표면 동일성 ────────────────────────────────────────

def test_all_three_accept_common_flags():
    """3종 모두 --dry-run / --non-interactive / --no-backup 을 인식해야 한다"""
    for script in (TF, PS, FB):
        text = script.read_text(encoding="utf-8")
        for flag in ("--dry-run", "--non-interactive", "--no-backup"):
            assert flag in text, f"{script.name}: {flag} 미지원"


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
