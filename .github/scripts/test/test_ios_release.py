"""iOS 릴리스 판단 로직 테스트 (이슈 #643). 네트워크와 Apple 호출 없음."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ios_release as ir


# ── 버전 파싱과 비교 ─────────────────────────────────────────────────
@pytest.mark.parametrize("s,expected", [("2.1.2", (2, 1, 2)), ("2.1", (2, 1, 0)), ("3", (3, 0, 0)),
                                        ("2.1.2b", None), ("", None), (None, None)])
def test_parse_version(s, expected):
    # Review Focus 1: 비정상 문자열에도 죽지 않는다
    assert ir.parse_version(s) == expected


def test_version_compare_numeric():
    assert ir.parse_version("1.20") > ir.parse_version("1.3")


def test_format_and_next_patch():
    assert ir.format_version((2, 1, 3)) == "2.1.3"
    assert ir.next_patch("2.1.2") == "2.1.3"
    assert ir.next_patch("2.1") == "2.1.1"


def test_closed_max_uses_both_state_fields():
    vs = [{"version": "2.1.2", "appVersionState": None, "appStoreState": "READY_FOR_SALE"},
          {"version": "2.2.0", "appVersionState": "WAITING_FOR_REVIEW", "appStoreState": None},
          {"version": "1.45.0", "appVersionState": "READY_FOR_DISTRIBUTION", "appStoreState": None},
          {"version": "x", "appVersionState": "ACCEPTED", "appStoreState": None}]
    assert ir.closed_max(vs) == "2.1.2"


def test_closed_max_skips_malformed_and_empty():
    vs = [{"version": "2.1.2b", "appVersionState": "ACCEPTED", "appStoreState": None},
          {"version": None, "appVersionState": "ACCEPTED", "appStoreState": None},
          {"version": "", "appVersionState": "ACCEPTED", "appStoreState": None}]
    assert ir.closed_max(vs) is None
    assert ir.closed_max([]) is None


def test_developer_rejected_is_open():
    assert ir.closed_max([{"version": "3.0.0", "appVersionState": "DEVELOPER_REJECTED",
                           "appStoreState": None}]) is None


@pytest.mark.parametrize("current,closed,mode,ok,version,changed", [
    ("2.1.3", "2.1.2", "test", True, "2.1.3", False),
    ("2.1.2", "2.1.2", "test", True, "2.1.3", True),
    ("2.1.0", "2.1.2", "test", True, "2.1.3", True),
    ("2.1.2", None, "test", True, "2.1.2", False),
    ("2.1.2", "2.1.2", "release", False, "2.1.2", False),
    ("2.1.3", "2.1.2", "release", True, "2.1.3", False)])
def test_decide_version(current, closed, mode, ok, version, changed):
    r = ir.decide_version(current, closed, mode)
    assert (r["ok"], r["version"], r["changed"]) == (ok, version, changed)


def test_decide_version_reasons():
    assert ir.decide_version("2.1.2", "2.1.2", "test")["reason"] == "2.1.2 출시되어 닫힘, 빌드 버전 2.1.3"
    assert "낮음" in ir.decide_version("2.1.0", "2.1.2", "test")["reason"]
    assert "version.yml" in ir.decide_version("2.1.2", "2.1.2", "release")["reason"]


# ── 업로드 오류 분류 (Apple 실제 문구 샘플) ──────────────────────────
CLASSIFY_CASES = [
    ("[altool] Invalid Pre-Release Train. The train version '2.1.2' is closed for new build submissions (90186)",
     "train_closed", None, "2.1.2"),
    ("This bundle is invalid. The value for key CFBundleShortVersionString [2.1.2] in the Info.plist file "
     "must contain a higher version than that of the previously approved version [2.1.2].",
     "train_closed", None, "2.1.2"),
    ("ERROR ITMS-90478: Invalid Version. The build with the version \"4.4\" can't be imported because "
     "a later version has been closed for new build submissions.", "train_closed", None, None),
    ("The value for key CFBundleVersion [4001] in the Info.plist file must contain a higher version than "
     "that of the previously uploaded version [20240719]. With error code STATE_ERROR.VALIDATION_ERROR.90061",
     "too_low", 20240719, None),
    ("The bundle version must be higher than the previously uploaded version: '86677590'.",
     "too_low", 86677590, None),
    ("ERROR ITMS-90189: \"Redundant Binary Upload. You've already uploaded a build with build number "
     "'86677440' for version number '2.1.3'.\"", "duplicate", None, None),
    ("ENTITY_ERROR.ATTRIBUTE.INVALID.DUPLICATE (-19232)", "duplicate", None, None),
]


@pytest.mark.parametrize("log,kind,required,closed", CLASSIFY_CASES)
def test_classify_upload_error_samples(log, kind, required, closed):
    r = ir.classify_upload_error(log)
    assert (r["kind"], r["required_build"], r["closed_version"]) == (kind, required, closed)
    assert r["reason_line"]


def test_classify_strips_ansi_and_handles_korean():
    # Review Focus 2: 색상 코드와 한국어 출력이 섞여도 분류되고 사유에 색상 코드가 남지 않는다
    r = ir.classify_upload_error("\x1b[31m[!] Could not find App with bundle id\x1b[0m\n오류 발생")
    assert r["kind"] == "other" and "\x1b" not in r["reason_line"]
    r = ir.classify_upload_error("\x1b[31m[!] ERROR ITMS-90189: Redundant Binary Upload\x1b[0m\n다음 단계 실패")
    assert r["kind"] == "duplicate" and "\x1b" not in r["reason_line"] and "ITMS-90189" in r["reason_line"]
    r = ir.classify_upload_error("\x1b[1;31m실패: 업로드 중 오류\x1b[0m")
    assert "\x1b" not in r["reason_line"]


def test_classify_empty_log():
    r = ir.classify_upload_error("")
    assert r["kind"] == "other" and r["reason_line"] == "업로드 실패 (사유를 로그에서 찾지 못함)"


def test_classify_priority_train_closed_over_duplicate():
    r = ir.classify_upload_error("ITMS-90189 Redundant Binary Upload\nITMS-90186 train version '2.1.2' is closed")
    assert r["kind"] == "train_closed" and r["closed_version"] == "2.1.2"


def test_classify_reason_line_truncated_and_trimmed():
    r = ir.classify_upload_error("   ERROR " + "x" * 500)
    assert len(r["reason_line"]) <= 300 and not r["reason_line"].startswith(" ")


def test_reason_lines_have_no_forbidden_punctuation():
    for log, *_ in CLASSIFY_CASES:
        assert "\u00b7" not in ir.classify_upload_error(log)["reason_line"]
    assert "\u2014" not in ir.decide_version("2.1.2", "2.1.2", "release")["reason"]


# ── CLI ───────────────────────────────────────────────────────────────
def _clear_asc(monkeypatch):
    for k in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_PATH"):
        monkeypatch.setenv(k, "")


def test_precheck_fallback_without_token(monkeypatch, capsys):
    _clear_asc(monkeypatch)
    rc = ir.main(["precheck-version", "--mode", "test", "--version", "2.1.2", "--bundle-id", "com.a.b"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0 and out["ok"] is True and out["fallback"] is True
    assert out["version"] == "2.1.2" and out["changed"] is False


def test_precheck_fallback_on_asc_error(monkeypatch, capsys):
    monkeypatch.setattr(ir.asc_client, "token_from_env", lambda: "tok")

    def boom(*a, **k):
        raise ir.asc_client.AscError("HTTP 403", status=403)

    monkeypatch.setattr(ir.asc_client, "find_app_id", boom)
    rc = ir.main(["precheck-version", "--mode", "release", "--version", "2.1.2", "--bundle-id", "com.a.b"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0 and out["fallback"] is True and "ASC 조회 불가" in out["reason"]


def _patch_closed(monkeypatch, closed_version="2.1.2"):
    monkeypatch.setattr(ir.asc_client, "token_from_env", lambda: "tok")
    monkeypatch.setattr(ir.asc_client, "find_app_id", lambda b, t: "APP1")
    monkeypatch.setattr(ir.asc_client, "list_app_store_versions", lambda a, t: [
        {"version": closed_version, "appVersionState": "READY_FOR_DISTRIBUTION", "appStoreState": None}])


def test_precheck_release_closed_exits_1(monkeypatch, capsys):
    _patch_closed(monkeypatch)
    rc = ir.main(["precheck-version", "--mode", "release", "--version", "2.1.2", "--bundle-id", "com.a.b"])
    cap = capsys.readouterr()
    assert rc == 1 and json.loads(cap.out.strip())["ok"] is False
    assert "::error::" in cap.err


def test_precheck_test_closed_bumps_and_writes_output(monkeypatch, capsys, tmp_path):
    _patch_closed(monkeypatch)
    out_file = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    rc = ir.main(["precheck-version", "--mode", "test", "--version", "2.1.2", "--bundle-id", "com.a.b"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0 and out["version"] == "2.1.3" and out["changed"] is True and out["closed_max"] == "2.1.2"
    text = out_file.read_text()
    assert "version=2.1.3" in text and "changed=true" in text and "reason=" in text


def test_precheck_app_not_found_falls_back(monkeypatch, capsys):
    monkeypatch.setattr(ir.asc_client, "token_from_env", lambda: "tok")
    monkeypatch.setattr(ir.asc_client, "find_app_id", lambda b, t: None)
    rc = ir.main(["precheck-version", "--mode", "test", "--version", "2.1.2", "--bundle-id", "com.a.b"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0 and out["fallback"] is True and out["version"] == "2.1.2"


def test_classify_error_cli(tmp_path, capsys):
    log = tmp_path / "up.log"
    log.write_text("ITMS-90189: Redundant Binary Upload", encoding="utf-8")
    assert ir.main(["classify-error", "--log", str(log)]) == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is True and out["kind"] == "duplicate"


def test_classify_error_cli_missing_file(tmp_path, capsys):
    assert ir.main(["classify-error", "--log", str(tmp_path / "nope.log")]) == 0
    assert json.loads(capsys.readouterr().out.strip())["kind"] == "other"


# ── archive-upload (Task 4) ──────────────────────────────────────────
import plistlib
import zipfile

ANSI_RED = "\x1b[31m"
LOG_DUP = "[!] ITMS-90189: Redundant Binary Upload. You've already uploaded a build with build number"
LOG_TRAIN = "ITMS-90186: Invalid Pre-Release Train. The train version '2.1.2' is closed for new build submissions"
LOG_LOW = ("ITMS-90061: Invalid Bundle. The bundle must contain a higher version than that of the "
           "previously uploaded version [99999999]")


class Fake:
    """xcodebuild와 fastlane을 대신하는 가짜 run_cmd. 실제 Apple 호출은 없다."""

    def __init__(self, root, fastlane=None, appex_build=None, flutter_seen=None):
        self.root = root
        self.fastlane = list(fastlane or [(0, "")])
        self.appex_build = appex_build      # 확장에 다른 번호를 쓰고 싶을 때
        self.calls = []                      # (kind, cmd, env)
        self.last = {}

    def kinds(self, k):
        return [c for c in self.calls if c[0] == k]

    def __call__(self, cmd, cwd, env):
        if cmd[0] == "flutter":
            self.calls.append(("flutter", cmd, env))
            return 0, ""
        if cmd[0] == "xcodebuild" and "archive" in cmd and "-exportArchive" not in cmd:
            self.last = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in cmd if "=" in a}
            self.calls.append(("archive", cmd, env))
            return 0, ""
        if cmd[0] == "xcodebuild" and "-exportArchive" in cmd:
            self.calls.append(("export", cmd, env))
            ipa_dir = Path(cwd) / "build" / "ipa"
            ipa_dir.mkdir(parents=True, exist_ok=True)
            n, v = self.last["FLUTTER_BUILD_NUMBER"], self.last["FLUTTER_BUILD_NAME"]
            ext_n = self.appex_build or n
            with zipfile.ZipFile(ipa_dir / "App.ipa", "w") as z:
                z.writestr("Payload/Runner.app/Info.plist", plistlib.dumps(
                    {"CFBundleVersion": n, "CFBundleShortVersionString": v}, fmt=plistlib.FMT_BINARY))
                z.writestr("Payload/Runner.app/PlugIns/Widget.appex/Info.plist", plistlib.dumps(
                    {"CFBundleVersion": ext_n, "CFBundleShortVersionString": v}, fmt=plistlib.FMT_BINARY))
            return 0, ""
        if cmd[:3] == ["bundle", "exec", "fastlane"]:
            self.calls.append(("fastlane", cmd, dict(env)))
            return self.fastlane.pop(0) if self.fastlane else (0, "")
        raise AssertionError(f"예상하지 못한 명령: {cmd}")


@pytest.fixture
def env(tmp_path, monkeypatch):
    ios = tmp_path / "ios"
    ios.mkdir()
    (ios / "ExportOptions.plist").write_bytes(plistlib.dumps({"method": "app-store"}))
    for k in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_PATH", "BUILD_NUMBER_FLOOR", "MAX_ATTEMPTS",
              "APP_IDENTIFIER", "IOS_PROVISIONING_PROFILE_NAME", "GITHUB_OUTPUT", "DEPLOY_MODE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APP_ROOT", str(tmp_path))
    monkeypatch.setenv("VERSION", "2.1.3")
    monkeypatch.setenv("MODE", "test")
    monkeypatch.setattr(ir, "sleep", lambda s: None)
    clock = iter(range(1704067200 + 100_000, 1704067200 + 100_000_000))
    monkeypatch.setattr(ir.time, "time", lambda: next(clock))
    # 기본은 ASC 불가
    monkeypatch.setattr(ir.asc_client, "token_from_env", lambda: None)
    return tmp_path


def use_fake(monkeypatch, fake):
    monkeypatch.setattr(ir, "run_cmd", fake)


def asc(monkeypatch, exists=lambda n: False, closed=None):
    """ASC를 쓸 수 있는 환경으로 만든다. exists(번호) -> bool 또는 예외."""
    monkeypatch.setenv("APP_IDENTIFIER", "com.a.b")
    monkeypatch.setattr(ir.asc_client, "token_from_env", lambda: "tok")
    monkeypatch.setattr(ir.asc_client, "find_app_id", lambda b, t: "app1")
    monkeypatch.setattr(ir.asc_client, "recent_max_build", lambda a, t: None)
    monkeypatch.setattr(ir.asc_client, "build_exists", lambda a, n, t: exists(n))
    monkeypatch.setattr(ir.asc_client, "list_app_store_versions", lambda a, t: closed or [])


def run(capsys, phase):
    rc = ir.main(["archive-upload", "--phase", phase])
    cap = capsys.readouterr()
    lines = [l for l in cap.out.splitlines() if l.strip()]
    assert len(lines) == 1, f"stdout은 JSON 한 줄이어야 함: {cap.out!r}"
    return rc, json.loads(lines[0])


def both(capsys, monkeypatch, fake):
    use_fake(monkeypatch, fake)
    rc, b = run(capsys, "build")
    assert rc == 0, b
    return run(capsys, "upload")


def test_build_phase_passes_build_settings_and_verifies(env, monkeypatch, capsys):
    fake = Fake(env)
    use_fake(monkeypatch, fake)
    src = env / "ios" / "ExportOptions.plist"
    before = src.read_bytes()
    rc, out = run(capsys, "build")
    assert rc == 0 and out["ok"] is True and out["attempts"] == 1
    cmd = fake.kinds("archive")[0][1]
    for want in (f"FLUTTER_BUILD_NUMBER={out['build_number']}", f"CURRENT_PROJECT_VERSION={out['build_number']}",
                 "FLUTTER_BUILD_NAME=2.1.3", "MARKETING_VERSION=2.1.3"):
        assert want in cmd
    rt = plistlib.loads((env / "ios/build/ExportOptions.runtime.plist").read_bytes())
    assert rt["manageAppVersionAndBuildNumber"] is False and rt["method"] == "app-store"
    assert src.read_bytes() == before  # 원본 불변
    export = fake.kinds("export")[0][1]
    assert export[export.index("-exportOptionsPlist") + 1] == "build/ExportOptions.runtime.plist"
    st = json.loads((env / "ios/build/ios_release_state.json").read_text())
    assert st["version"] == "2.1.3" and st["build_number"] == out["build_number"] and st["attempt"] == 1
    assert st["ipa_path"].endswith("App.ipa")


def test_build_phase_fails_on_extension_mismatch(env, monkeypatch, capsys):
    fake = Fake(env, appex_build="12345")
    use_fake(monkeypatch, fake)
    rc, out = run(capsys, "build")
    assert rc == 1 and out["ok"] is False
    assert "Widget.appex" in out["reason_line"] and "12345" in out["reason_line"]
    assert not fake.kinds("fastlane")
    assert not (env / "ios/build/ios_release_state.json").exists()


def test_upload_success_first_try(env, monkeypatch, capsys):
    fake = Fake(env)
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 0 and out["attempts"] == 1 and len(fake.kinds("fastlane")) == 1


def test_upload_duplicate_then_success(env, monkeypatch, capsys):
    # ASC 조회에 그 번호가 보이지 않는 경우(반영 지연 등)에만 재시도한다. 보이면 아래 test_no_reupload 가 막는다.
    asc(monkeypatch)
    fake = Fake(env, fastlane=[(1, LOG_DUP), (0, "")])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 0 and out["attempts"] == 2 and len(fake.kinds("archive")) == 2
    nums = [int([a for a in c[1] if a.startswith("FLUTTER_BUILD_NUMBER=")][0].split("=")[1])
            for c in fake.kinds("archive")]
    assert nums[1] > nums[0]
    assert fake.kinds("fastlane")[1][2]["BUILD_NUMBER"] == str(nums[1])


def test_upload_too_low_uses_required_floor(env, monkeypatch, capsys):
    asc(monkeypatch)
    fake = Fake(env, fastlane=[(1, LOG_LOW), (0, "")])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 0 and out["build_number"] == 100000000


def test_train_closed_test_mode_bumps_version(env, monkeypatch, capsys):
    # 시작 버전이 닫힌 버전과 같아야 "바뀌었다"를 검증할 수 있다
    monkeypatch.setenv("VERSION", "2.1.2")
    asc(monkeypatch)
    fake = Fake(env, fastlane=[(1, LOG_TRAIN), (0, "")])
    rc, out = both(capsys, monkeypatch, fake)
    assert "FLUTTER_BUILD_NAME=2.1.2" in fake.kinds("archive")[0][1]
    assert rc == 0 and out["version"] == "2.1.3"
    assert "FLUTTER_BUILD_NAME=2.1.3" in fake.kinds("archive")[1][1]
    assert fake.kinds("fastlane")[1][2]["APP_VERSION"] == "2.1.3"


def test_train_closed_uses_closed_version_from_log(env, monkeypatch, capsys):
    monkeypatch.setenv("VERSION", "2.1.2")
    asc(monkeypatch)
    fake = Fake(env, fastlane=[(1, LOG_TRAIN), (0, "")])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 0 and out["version"] == "2.1.3"
    assert "FLUTTER_BUILD_NAME=2.1.3" in fake.kinds("archive")[1][1]


def test_train_closed_without_version_uses_asc(env, monkeypatch, capsys):
    monkeypatch.setenv("VERSION", "2.1.2")
    asc(monkeypatch, closed=[{"version": "2.1.5", "appVersionState": "ACCEPTED", "appStoreState": None}])
    fake = Fake(env, fastlane=[(1, "ITMS-90478: later version has been closed"), (0, "")])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 0 and out["version"] == "2.1.6"


def test_train_closed_release_mode_fails(env, monkeypatch, capsys):
    monkeypatch.setenv("MODE", "release")
    asc(monkeypatch)
    fake = Fake(env, fastlane=[(1, LOG_TRAIN)])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 1 and len(fake.kinds("archive")) == 1 and len(fake.kinds("fastlane")) == 1


def test_no_retry_without_asc_token(env, monkeypatch, capsys):
    fake = Fake(env, fastlane=[(1, LOG_DUP)])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 1 and len(fake.kinds("fastlane")) == 1
    assert "ASC 조회 불가로 재업로드 여부를 확인할 수 없어 중단" in out["reason_line"]


def test_no_retry_when_asc_lookup_errors(env, monkeypatch, capsys):
    def boom(n):
        raise ir.asc_client.AscError("ASC HTTP 500")
    asc(monkeypatch, exists=boom)
    fake = Fake(env, fastlane=[(1, LOG_DUP)])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 1 and len(fake.kinds("fastlane")) == 1 and len(fake.kinds("archive")) == 1
    assert "재업로드 여부를 확인할 수 없어 중단" in out["reason_line"]


def test_no_reupload_when_build_already_exists(env, monkeypatch, capsys):
    asc(monkeypatch, exists=lambda n: True)
    fake = Fake(env, fastlane=[(1, "pilot 처리 대기 실패 ITMS-90189")])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 1 and len(fake.kinds("fastlane")) == 1
    assert "같은 번호의 빌드가 이미" in out["reason_line"] and "재업로드하지 않습니다" in out["reason_line"]
    assert "다시 실행하면 새 번호" in out["reason_line"]


def test_build_exists_rechecked_three_times_before_retry(env, monkeypatch, capsys):
    seen = []
    asc(monkeypatch, exists=lambda n: seen.append(n) or False)
    fake = Fake(env, fastlane=[(1, LOG_DUP), (0, "")])
    both(capsys, monkeypatch, fake)
    assert len(seen) == 3 and len(set(seen)) == 1


def test_other_error_fails_immediately(env, monkeypatch, capsys):
    asc(monkeypatch)
    fake = Fake(env, fastlane=[(1, "ERROR: Authentication credentials are missing or invalid")])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 1 and len(fake.kinds("fastlane")) == 1 and "Authentication" in out["reason_line"]


def test_attempts_exhausted(env, monkeypatch, capsys):
    asc(monkeypatch)
    fake = Fake(env, fastlane=[(1, LOG_DUP)] * 10)
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 1 and len(fake.kinds("fastlane")) == 5 and out["attempts"] == 5
    assert "ITMS-90189" in out["reason_line"]


def test_max_attempts_env(env, monkeypatch, capsys):
    monkeypatch.setenv("MAX_ATTEMPTS", "2")
    asc(monkeypatch)
    fake = Fake(env, fastlane=[(1, LOG_DUP)] * 10)
    rc, _ = both(capsys, monkeypatch, fake)
    assert rc == 1 and len(fake.kinds("fastlane")) == 2


def test_minimal_env_workflow_dispatch(env, monkeypatch, capsys):
    # Review Focus 4: VERSION, MODE, APP_ROOT만으로 build와 upload 성공
    rc, out = both(capsys, monkeypatch, Fake(env))
    assert rc == 0 and out["ok"] is True


def test_upload_passes_final_numbers_to_fastlane(env, monkeypatch, capsys):
    fake = Fake(env)
    rc, out = both(capsys, monkeypatch, fake)
    e = fake.kinds("fastlane")[0][2]
    assert e["BUILD_NUMBER"] == str(out["build_number"]) and e["APP_VERSION"] == "2.1.3"
    assert e["IPA_PATH"] == out["ipa_path"] and e["IPA_PATH"].endswith("App.ipa")
    assert fake.kinds("fastlane")[0][1] == ["bundle", "exec", "fastlane", "deploy"]


def test_test_mode_pins_store_only(env, monkeypatch, capsys):
    fake = Fake(env)
    both(capsys, monkeypatch, fake)
    assert fake.kinds("fastlane")[0][2]["DEPLOY_MODE"] == "store_only"


@pytest.mark.parametrize("existing", ["store_submit", "", "full"])
def test_test_mode_overrides_existing_deploy_mode(env, monkeypatch, capsys, existing):
    # 이미 다른 값이 들어와 있어도 테스트 빌드가 심사 제출까지 가면 안 된다 (#601)
    monkeypatch.setenv("DEPLOY_MODE", existing)
    fake = Fake(env)
    both(capsys, monkeypatch, fake)
    assert fake.kinds("fastlane")[0][2]["DEPLOY_MODE"] == "store_only"


def test_release_mode_does_not_touch_deploy_mode(env, monkeypatch, capsys):
    monkeypatch.setenv("MODE", "release")
    monkeypatch.setenv("DEPLOY_MODE", "store_submit")
    fake = Fake(env)
    both(capsys, monkeypatch, fake)
    assert fake.kinds("fastlane")[0][2]["DEPLOY_MODE"] == "store_submit"


@pytest.mark.parametrize("log", [
    "Warning: DUPLICATE localization entry ... timeout",
    "Build 1-19232 done. ERROR: network",
])
def test_duplicate_pattern_does_not_match_unrelated_text(log):
    assert ir.classify_upload_error(log)["kind"] == "other"


def test_duplicate_matches_entity_error_code():
    assert ir.classify_upload_error("ENTITY_ERROR.ATTRIBUTE.INVALID.DUPLICATE (-19232)")["kind"] == "duplicate"
    assert ir.classify_upload_error("failed with -19232")["kind"] == "duplicate"


def test_github_output_is_single_line_key_value(env, monkeypatch, capsys):
    out_file = env / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    multi = f"{ANSI_RED}[!] 첫 줄 실패\n두 번째 줄\r\n세 번째"
    fake = Fake(env, fastlane=[(1, multi)])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 1
    lines = out_file.read_text(encoding="utf-8").splitlines()
    assert all("=" in l.split(" ")[0] for l in lines), lines
    keys = [l.split("=", 1)[0] for l in lines]
    assert keys.count("reason_line") == 1
    rl = [l for l in lines if l.startswith("reason_line=")][0]
    assert "\x1b" not in rl and "첫 줄" in rl
    for k in ("build_number", "version", "attempts", "ipa_path", "built_at_utc"):
        assert k in keys


def test_success_github_output_keys(env, monkeypatch, capsys):
    out_file = env / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    both(capsys, monkeypatch, Fake(env))
    keys = {l.split("=", 1)[0] for l in out_file.read_text().splitlines()}
    assert {"build_number", "version", "attempts", "ipa_path", "built_at_utc"} <= keys


def test_train_closed_unparseable_version_does_not_crash(env, monkeypatch, capsys):
    asc(monkeypatch)
    fake = Fake(env, fastlane=[(1, "ITMS-90186: train version '1.2.3' is closed")])
    monkeypatch.setattr(ir, "next_patch", lambda s: (_ for _ in ()).throw(ValueError("버전 형식을 해석할 수 없습니다: 'x'")))
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 1 and len(fake.kinds("fastlane")) == 1
    assert "해석할 수 없습니다" in out["reason_line"]


def test_train_closed_real_next_patch_valueerror_path():
    with pytest.raises(ValueError):
        ir.next_patch("2.1.2b")


def test_upload_phase_without_state_file(env, monkeypatch, capsys):
    use_fake(monkeypatch, Fake(env))
    rc, out = run(capsys, "upload")
    assert rc == 1 and "상태 파일이 없습니다" in out["reason_line"]


def test_upload_phase_with_corrupt_state_file(env, monkeypatch, capsys):
    fake = Fake(env)
    use_fake(monkeypatch, fake)
    state = env / "ios/build"
    state.mkdir(parents=True)
    (state / "ios_release_state.json").write_text("{깨진 json", encoding="utf-8")
    rc, out = run(capsys, "upload")
    assert rc == 1 and "손상" in out["reason_line"] and not fake.kinds("fastlane")
    (state / "ios_release_state.json").write_text('{"version": "1"}', encoding="utf-8")
    rc, out = run(capsys, "upload")
    assert rc == 1 and "손상" in out["reason_line"] and not fake.kinds("fastlane")


def test_retry_does_not_rebuild_flutter(env, monkeypatch, capsys):
    asc(monkeypatch)
    fake = Fake(env, fastlane=[(1, LOG_DUP), (1, LOG_DUP), (0, "")])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 0 and len(fake.kinds("archive")) == 3 and not fake.kinds("flutter")


def test_missing_required_env_fails_clearly(env, monkeypatch, capsys):
    monkeypatch.delenv("VERSION")
    use_fake(monkeypatch, Fake(env))
    rc, out = run(capsys, "build")
    assert rc == 1 and "VERSION" in out["reason_line"]
    monkeypatch.setenv("VERSION", "1.0.0")
    monkeypatch.setenv("MODE", "prod")
    rc, out = run(capsys, "build")
    assert rc == 1 and "MODE" in out["reason_line"]


def test_secrets_are_scrubbed_from_reason(env, monkeypatch, capsys):
    monkeypatch.setenv("ASC_PRIVATE_TOKEN_X", "SUPERSECRETVALUE123")
    fake = Fake(env, fastlane=[(1, "[!] failed with SUPERSECRETVALUE123 inside")])
    rc, out = both(capsys, monkeypatch, fake)
    assert rc == 1 and "SUPERSECRETVALUE123" not in json.dumps(out)
    assert "SUPERSECRETVALUE123" not in (env / "ios/build/upload_attempt_1.log").read_text()


def test_attempt_logs_saved_per_try(env, monkeypatch, capsys):
    asc(monkeypatch)
    fake = Fake(env, fastlane=[(1, LOG_DUP), (0, "ok 성공")])
    both(capsys, monkeypatch, fake)
    assert "ITMS-90189" in (env / "ios/build/upload_attempt_1.log").read_text()
    assert (env / "ios/build/upload_attempt_2.log").exists()


def test_verify_ipa_covers_watch_and_appclip(tmp_path):
    ipa = tmp_path / "a.ipa"
    good = plistlib.dumps({"CFBundleVersion": "5", "CFBundleShortVersionString": "1.0.0"})
    bad = plistlib.dumps({"CFBundleVersion": "4", "CFBundleShortVersionString": "1.0.0"})
    with zipfile.ZipFile(ipa, "w") as z:
        z.writestr("Payload/A.app/Info.plist", good)
        z.writestr("Payload/A.app/Watch/W.app/Info.plist", good)
        z.writestr("Payload/A.app/Watch/W.app/PlugIns/E.appex/Info.plist", bad)
        z.writestr("Payload/A.app/AppClips/C.app/Info.plist", bad)
        z.writestr("Payload/A.app/Frameworks/F.framework/Info.plist", bad)  # 프레임워크는 대상 아님
    probs = ir.verify_ipa(ipa, "1.0.0", 5)
    assert len(probs) == 2
    assert any("E.appex" in p for p in probs) and any("C.app" in p for p in probs)
    assert not any("F.framework" in p for p in probs)
    assert "CFBundleVersion=4 (기대 5)" in probs[0] or "CFBundleVersion=4 (기대 5)" in probs[1]


def test_verify_ipa_bad_zip_and_no_app(tmp_path):
    bad = tmp_path / "x.ipa"
    bad.write_text("not zip")
    assert ir.verify_ipa(bad, "1", 1)
    empty = tmp_path / "e.ipa"
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("readme", "x")
    assert ir.verify_ipa(empty, "1", 1)


def test_no_forbidden_typography_in_source():
    src = (Path(ir.__file__)).read_text(encoding="utf-8")
    assert "·" not in src and "—" not in src


# ── asc-status (조회 전용 수동 실행 워크플로가 부른다, #651) ─────────────
def _patch_status(monkeypatch, versions=None, recent=45105):
    monkeypatch.setattr(ir.asc_client, "token_from_env", lambda: "tok")
    monkeypatch.setattr(ir.asc_client, "find_app_id", lambda b, t: "APP1")
    monkeypatch.setattr(ir.asc_client, "list_app_store_versions", lambda a, t: versions if versions is not None else [
        {"version": "2.1.2", "appVersionState": None, "appStoreState": "READY_FOR_SALE"},
        {"version": "2.1.3", "appVersionState": "WAITING_FOR_REVIEW", "appStoreState": None},
        {"version": "2.0.9", "appVersionState": "REPLACED_WITH_NEW_VERSION", "appStoreState": None}])
    monkeypatch.setattr(ir.asc_client, "recent_max_build", lambda a, t: recent)


def test_asc_status_reports_versions_and_closed_max(monkeypatch, capsys):
    _patch_status(monkeypatch)
    rc = ir.main(["asc-status", "--bundle-id", "com.a.b"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0 and out["ok"] is True and out["closed_max"] == "2.1.2" and out["recent_max_build"] == 45105
    # 최신 버전이 먼저, 닫힘 여부가 항목마다 표시된다
    assert [v["version"] for v in out["versions"]] == ["2.1.3", "2.1.2", "2.0.9"]
    assert {v["version"]: v["closed"] for v in out["versions"]} == {"2.1.3": False, "2.1.2": True, "2.0.9": True}


def test_asc_status_writes_step_summary(monkeypatch, capsys, tmp_path):
    _patch_status(monkeypatch)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert ir.main(["asc-status", "--bundle-id", "com.a.b"]) == 0
    text = summary.read_text(encoding="utf-8")
    assert "2.1.2" in text and "READY_FOR_SALE" in text and "45105" in text
    # 키 값이나 발급자 ID가 요약에 섞이면 안 된다
    assert "tok" not in text.replace("token", "")


def test_asc_status_without_token_fails_loudly(monkeypatch, capsys):
    monkeypatch.setattr(ir.asc_client, "token_from_env", lambda: None)
    rc = ir.main(["asc-status", "--bundle-id", "com.a.b"])
    out = json.loads(capsys.readouterr().out.strip())
    # 조회가 목적인 명령이라 사전 점검과 달리 조용히 폴백하지 않는다
    assert rc == 1 and out["ok"] is False and "인증 정보" in out["reason"]


def test_asc_status_app_not_found_and_api_error(monkeypatch, capsys):
    _patch_status(monkeypatch)
    monkeypatch.setattr(ir.asc_client, "find_app_id", lambda b, t: None)
    assert ir.main(["asc-status", "--bundle-id", "com.a.b"]) == 1
    assert json.loads(capsys.readouterr().out.strip())["ok"] is False

    def boom(*a, **k):
        raise ir.asc_client.AscError("HTTP 403", status=403)
    _patch_status(monkeypatch)
    monkeypatch.setattr(ir.asc_client, "list_app_store_versions", boom)
    assert ir.main(["asc-status", "--bundle-id", "com.a.b"]) == 1
    assert "403" in json.loads(capsys.readouterr().out.strip())["reason"]


def test_asc_status_recent_build_failure_is_not_fatal(monkeypatch, capsys):
    # 최근 빌드 조회만 실패해도 버전 표는 보여준다
    _patch_status(monkeypatch)

    def boom(*a, **k):
        raise ir.asc_client.AscError("HTTP 403", status=403)
    monkeypatch.setattr(ir.asc_client, "recent_max_build", boom)
    rc = ir.main(["asc-status", "--bundle-id", "com.a.b"])
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0 and out["recent_max_build"] is None and out["closed_max"] == "2.1.2"


# E2E(elum)에서 사유가 "** ARCHIVE FAILED **" 배너만 나와 원인을 알 수 없던 결함 (#643)
XCODE_FAIL = (
    "Command line invocation:\n"
    "/Users/runner/work/elum/elum/client/ios/Runner.xcodeproj: error: No profile for team 'CUK22HY6YC' "
    "matching 'bad-profile' found: Xcode couldn't find any provisioning profiles matching 'CUK22HY6YC/bad-profile'. "
    "Install the profile (by dragging and dropping it onto Xcode's dock item) or select a different one.\n"
    "** ARCHIVE FAILED **\n")


def test_last_error_line_prefers_real_error_over_banner():
    line = ir._last_error_line(XCODE_FAIL)
    assert line.startswith("No profile for team") and "bad-profile" in line
    assert "ARCHIVE FAILED" not in line and "/Users/runner" not in line


def test_last_error_line_falls_back_to_banner_then_last_line():
    assert ir._last_error_line("building...\n** ARCHIVE FAILED **\n") == "** ARCHIVE FAILED **"
    assert ir._last_error_line("just some output\nlast line\n") == "last line"
    assert ir._last_error_line("") == "출력 없음"


def test_last_error_line_uses_latest_error_when_several():
    out = "a.swift: error: first problem\nb.swift: error: second problem\n** BUILD FAILED **\n"
    assert ir._last_error_line(out) == "second problem"



# ── #694: ITMS- 접두 없는 숫자만으로는 오류 코드로 보지 않는다 ───────────────
@pytest.mark.parametrize("log", [
    "Uploading build 90189 done",
    "network error: took 90186 ms",
    "elapsed 90062 ms, size 90478 bytes, build 90061",
])
def test_bare_numbers_are_not_error_codes(log):
    assert ir.classify_upload_error(log)["kind"] == "other"
