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
