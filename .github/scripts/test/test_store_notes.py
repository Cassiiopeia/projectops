"""스토어 릴리스 노트 언어별 준비 (#829).

지켜야 할 약속 두 개:
  1. `store_locales` 가 없으면 아무것도 하지 않는다 — 기존 사용자의 동작이 바뀌면 안 된다.
  2. 번역이 없는 언어도 **빈 채로 두지 않는다** — App Store Connect 가 빈 What's New 를 거부한다(실측).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "store_notes.py"
sys.path.insert(0, str(SCRIPT.parent))
import store_notes as sn  # noqa: E402

YML = '''metadata:
  template:
    options:
      store_locales: ["ko-KR", "en-US", "ja-JP", "zh-CN"]   # 설명
'''
KO = "- 알림 동작을 개선했어요"


def _run(*argv):
    r = subprocess.run([sys.executable, str(SCRIPT), *map(str, argv)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _ws(tmp_path, yml=YML, changelog=None):
    (tmp_path / "version.yml").write_text(yml, encoding="utf-8")
    (tmp_path / "default.txt").write_text(KO, encoding="utf-8")
    if changelog is not None:
        (tmp_path / "CHANGELOG.json").write_text(json.dumps(changelog), encoding="utf-8")
    return tmp_path


# ── 약속 1: 키가 없으면 아무것도 하지 않는다 ─────────────────────────
def test_without_store_locales_nothing_is_written(tmp_path):
    ws = _ws(tmp_path, yml="version: 1.0.0\nmetadata:\n  template:\n    options:\n      semver_auto: true\n")
    for platform, extra in (("play", ["--version-code", "9"]), ("ios", ["--out-dir", tmp_path / "out"])):
        out = _run("write", "--platform", platform, "--workspace", ws, "--version", "1.0.0",
                   "--default-file", ws / "default.txt", *extra)
        assert out == {"enabled": False}
    assert not (tmp_path / "android").exists() and not (tmp_path / "out").exists()


def test_missing_version_yml_is_disabled_not_crash(tmp_path):
    out = _run("write", "--platform", "ios", "--workspace", tmp_path, "--version", "1", "--out-dir", tmp_path / "o")
    assert out == {"enabled": False}


# ── 언어 코드 변환 ─────────────────────────────────────────────────
@pytest.mark.parametrize("given,play,ios", [
    ("ko-KR", "ko-KR", "ko"), ("en-US", "en-US", "en-US"), ("ja-JP", "ja-JP", "ja"),
    ("zh-CN", "zh-CN", "zh-Hans"),
    ("ko", "ko-KR", "ko"), ("ja", "ja-JP", "ja"), ("zh-Hans", "zh-CN", "zh-Hans"),  # 어느 표기로 적어도 같다
])
def test_locale_code_table(given, play, ios):
    assert sn.store_code("play", given) == play
    assert sn.store_code("ios", given) == ios


def test_unknown_locale_is_not_passed_to_a_store():
    """지어낸 코드를 넘기면 deliver 는 앱에 언어를 활성화하려 하고 supply 는 거부한다 — 넘기지 않는다."""
    assert sn.store_code("ios", "xx-YY") is None
    assert sn.store_code("play", "xx-YY") is None


# ── 언어 표: fastlane 목록에서 나온다 ────────────────────────────────
def test_every_mapping_lands_in_the_store_lists():
    for play_code, ios_code in sn.CANONICAL_TO_IOS.items():
        assert play_code in sn.PLAY_LANGUAGES, play_code
        assert ios_code in sn.IOS_LANGUAGES, (play_code, ios_code)


@pytest.mark.parametrize("given,play,ios", [
    ("fi-FI", "fi-FI", "fi"), ("sv-SE", "sv-SE", "sv"), ("iw-IL", "iw-IL", "he"), ("he", "iw-IL", "he"),
    ("es-419", "es-419", "es-MX"), ("no-NO", "no-NO", "no"), ("ar", "ar", "ar-SA"), ("zh-TW", "zh-TW", "zh-Hant"),
    ("zh-Hant", "zh-TW", "zh-Hant"), ("ko_KR", "ko-KR", "ko"), ("KO-kr", "ko-KR", "ko"),
    ("af", "af", None),          # Play 에만 있는 언어
    ("ur-PK", None, "ur-PK"),    # App Store 에만 있는 언어
])
def test_language_only_on_one_store(given, play, ios):
    assert sn.store_code("play", given) == play
    assert sn.store_code("ios", given) == ios


def test_unsupported_language_is_skipped_and_reported(tmp_path):
    ws = _ws(tmp_path, yml='options:\n  store_locales: ["ko-KR", "en-US", "af"]\n')
    out_dir = tmp_path / "o"
    out = _run("write", "--platform", "ios", "--workspace", ws, "--version", "1", "--out-dir", out_dir,
               "--default-file", ws / "default.txt")
    assert sorted(p.name for p in out_dir.iterdir()) == ["en-US.txt", "ko.txt"]
    assert out["unsupported"] == ["af"]
    play = _run("write", "--platform", "play", "--workspace", ws, "--version", "1", "--version-code", "3",
                "--default-file", ws / "default.txt")
    assert play["unsupported"] == [] and (ws / "android/fastlane/metadata/android/af/changelogs/3.txt").is_file()


def test_duplicate_locales_collapse():
    yml = 'options:\n  store_locales: ["ja", "ja-JP", "ko-KR"]\n'
    assert sn.read_store_locales(yml) == ["ja-JP", "ko-KR"]


# ── Play ───────────────────────────────────────────────────────────
def test_play_writes_each_language_with_translation_or_default(tmp_path):
    ws = _ws(tmp_path, changelog={"releases": [{"version": "1.2.3", "store_notes": {"en-US": "- Improved alerts", "ja-JP": "- 通知を改善"}}]})
    out = _run("write", "--platform", "play", "--workspace", ws, "--version", "1.2.3", "--version-code", "136",
               "--default-file", ws / "default.txt")
    base = ws / "android/fastlane/metadata/android"
    assert (base / "ko-KR/changelogs/136.txt").read_text(encoding="utf-8").strip() == KO
    assert (base / "en-US/changelogs/136.txt").read_text(encoding="utf-8").strip() == "- Improved alerts"
    assert (base / "ja-JP/changelogs/136.txt").read_text(encoding="utf-8").strip() == "- 通知を改善"
    # 번역이 없는 zh-CN 은 비우지 않고 기본 문구로 채운다
    assert (base / "zh-CN/changelogs/136.txt").read_text(encoding="utf-8").strip() == KO
    assert out["translated"] == ["en-US", "ja-JP"] and out["fell_back"] == ["zh-CN"]


def test_play_prunes_legacy_language_folder_not_in_list(tmp_path):
    # 옛 경로가 만든 ko-KR 이 목록(en-US 기본)에 없으면 이번 버전 노트를 치운다
    ws = _ws(tmp_path, yml='options:\n  store_locales: ["en-US", "ja-JP"]\n')
    legacy = ws / "android/fastlane/metadata/android/ko-KR/changelogs"
    legacy.mkdir(parents=True)
    (legacy / "7.txt").write_text("옛 한국어", encoding="utf-8")
    (legacy / "6.txt").write_text("이전 버전", encoding="utf-8")
    out = _run("write", "--platform", "play", "--workspace", ws, "--version", "1", "--version-code", "7",
               "--default-file", ws / "default.txt")
    assert out["pruned"] == ["ko-KR"]
    assert not (legacy / "7.txt").exists() and (legacy / "6.txt").exists()


def test_play_truncates_to_480_chars(tmp_path):
    ws = _ws(tmp_path)
    (ws / "default.txt").write_text("가" * 900, encoding="utf-8")
    _run("write", "--platform", "play", "--workspace", ws, "--version", "1", "--version-code", "1",
         "--default-file", ws / "default.txt")
    text = (ws / "android/fastlane/metadata/android/ko-KR/changelogs/1.txt").read_text(encoding="utf-8")
    assert len(text.strip()) <= 480


def test_play_needs_version_code(tmp_path):
    ws = _ws(tmp_path)
    out = _run("write", "--platform", "play", "--workspace", ws, "--version", "1", "--default-file", ws / "default.txt")
    assert out["ok"] is False


# ── iOS ────────────────────────────────────────────────────────────
def test_ios_uses_app_store_connect_codes_and_never_leaves_a_language_empty(tmp_path):
    ws = _ws(tmp_path, changelog={"releases": [{"version": "1.2.3", "store_notes": {"en-US": "- Improved alerts"}}]})
    out_dir = tmp_path / "ios-notes"
    out = _run("write", "--platform", "ios", "--workspace", ws, "--version", "1.2.3", "--out-dir", out_dir,
               "--default-file", ws / "default.txt")
    assert sorted(p.name for p in out_dir.iterdir()) == ["en-US.txt", "ja.txt", "ko.txt", "zh-Hans.txt"]
    for f in out_dir.iterdir():
        assert f.read_text(encoding="utf-8").strip(), f"{f.name} 이 비었다 — ASC 가 심사 제출을 거부한다"
    assert (out_dir / "en-US.txt").read_text(encoding="utf-8").strip() == "- Improved alerts"
    assert (out_dir / "ja.txt").read_text(encoding="utf-8").strip() == KO
    assert out["fell_back"] == ["ja-JP", "zh-CN"]


def test_ios_truncates_by_bytes(tmp_path):
    ws = _ws(tmp_path)
    (ws / "default.txt").write_text("가" * 3000, encoding="utf-8")  # 9000 바이트
    out_dir = tmp_path / "o"
    _run("write", "--platform", "ios", "--workspace", ws, "--version", "1", "--out-dir", out_dir, "--default-file", ws / "default.txt")
    assert len((out_dir / "ko.txt").read_bytes().strip()) <= 3800


# ── 기본 문구 결정 ─────────────────────────────────────────────────
def test_override_pins_default_language_text(tmp_path):
    ws = _ws(tmp_path)
    out_dir = tmp_path / "o"
    _run("write", "--platform", "ios", "--workspace", ws, "--version", "1", "--out-dir", out_dir,
         "--default-file", ws / "default.txt", "--override", "고정 문구")
    assert (out_dir / "ko.txt").read_text(encoding="utf-8").strip() == "고정 문구"


def test_blank_override_is_ignored(tmp_path):
    ws = _ws(tmp_path)
    out_dir = tmp_path / "o"
    _run("write", "--platform", "ios", "--workspace", ws, "--version", "1", "--out-dir", out_dir,
         "--default-file", ws / "default.txt", "--override", "   ")
    assert (out_dir / "ko.txt").read_text(encoding="utf-8").strip() == KO


def test_no_default_text_still_never_empty(tmp_path):
    ws = _ws(tmp_path)
    out_dir = tmp_path / "o"
    _run("write", "--platform", "ios", "--workspace", ws, "--version", "1", "--out-dir", out_dir)
    assert all(f.read_text(encoding="utf-8").strip() for f in out_dir.iterdir())


def test_broken_changelog_json_does_not_stop_the_release(tmp_path):
    ws = _ws(tmp_path)
    (ws / "CHANGELOG.json").write_text("{깨진 json", encoding="utf-8")
    out = _run("write", "--platform", "ios", "--workspace", ws, "--version", "1", "--out-dir", tmp_path / "o",
               "--default-file", ws / "default.txt")
    assert out["ok"] is True and out["translated"] == []


def test_monorepo_app_root_differs_from_repo_root(tmp_path):
    # version.yml 은 레포 루트, android/ 는 app/ 아래
    ws = _ws(tmp_path)
    app = ws / "app"
    app.mkdir()
    _run("write", "--platform", "play", "--workspace", ws, "--app-root", app, "--version", "1", "--version-code", "5",
         "--default-file", ws / "default.txt")
    assert (app / "android/fastlane/metadata/android/en-US/changelogs/5.txt").is_file()
    assert not (ws / "android").exists()


# ── PR 본문 → CHANGELOG.json store_notes (#829) ────────────────────
import os  # noqa: E402

import changelog_manager as cm  # noqa: E402

KO_BODY = """## Summary by CodeRabbit

## 릴리스 노트

* **새 기능**
  * 알림 동작 개선

* **버그 수정**
  * 로그인 오류 수정
"""
BLOCK = """
<!-- projectops:store-notes -->
<details><summary>Store release notes (translations)</summary>

**en-US**
- Improved alerts
- Fixed a sign-in error

**ja-JP**
- 通知を改善

</details>
<!-- /projectops:store-notes -->
"""


def test_extract_without_block_returns_body_unchanged():
    body, notes = cm.extract_store_notes(KO_BODY)
    assert body == KO_BODY and notes == {}


def test_extract_splits_languages_and_removes_block():
    body, notes = cm.extract_store_notes(KO_BODY + BLOCK)
    assert notes == {"en-US": "- Improved alerts\n- Fixed a sign-in error", "ja-JP": "- 通知を改善"}
    assert "projectops:store-notes" not in body and "Improved" not in body and "details" not in body


def test_korean_parser_result_is_identical_with_or_without_block():
    """번역 블록이 한국어 카테고리에 섞이면 안 된다 — 블록 유무와 상관없이 같은 파싱 결과."""
    plain = cm._parse_summary_markdown(KO_BODY)
    body, _ = cm.extract_store_notes(KO_BODY + BLOCK)
    assert cm._parse_summary_markdown(body) == plain


def _run_update(tmp_path, monkeypatch, body, version="1.2.3"):
    (tmp_path / "pr_body.md").write_text(body, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    for k, v in {"VERSION": version, "PROJECT_TYPE": "flutter", "TODAY": "2026-10-10",
                 "TIMESTAMP": "2026-10-10 00:00:00", "PR_NUMBER": "1"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("PR_BODY_PATH", raising=False)
    assert cm.cmd_update_from_summary() == 0
    return json.loads((tmp_path / "CHANGELOG.json").read_text(encoding="utf-8"))["releases"][0]


def test_update_from_summary_stores_store_notes_only_when_present(tmp_path, monkeypatch):
    with_block = _run_update(tmp_path, monkeypatch, KO_BODY + BLOCK)
    assert with_block["store_notes"]["ja-JP"] == "- 通知を改善"
    assert "Improved" not in with_block["raw_summary"]

    # 블록이 없는 릴리스는 키 자체가 없다 (기존 CHANGELOG.json 모양 무변화)
    (tmp_path / "CHANGELOG.json").unlink()
    without = _run_update(tmp_path, monkeypatch, KO_BODY, version="1.2.4")
    assert "store_notes" not in without


def test_store_notes_flow_end_to_end_into_files(tmp_path, monkeypatch):
    """PR 본문 → CHANGELOG.json → 언어별 파일까지 한 줄로 이어진다."""
    _run_update(tmp_path, monkeypatch, KO_BODY + BLOCK)
    (tmp_path / "version.yml").write_text(YML, encoding="utf-8")
    (tmp_path / "default.txt").write_text(KO, encoding="utf-8")
    out_dir = tmp_path / "o"
    _run("write", "--platform", "ios", "--workspace", tmp_path, "--version", "1.2.3", "--out-dir", out_dir,
         "--default-file", tmp_path / "default.txt")
    assert (out_dir / "ja.txt").read_text(encoding="utf-8").strip() == "- 通知を改善"
    assert (out_dir / "zh-Hans.txt").read_text(encoding="utf-8").strip() == KO   # 번역 없는 언어는 기본 문구


def test_standalone_bold_line_is_not_taken_for_a_language_heading():
    """번역 안의 `**New**` 같은 굵은 줄이 언어 제목으로 읽히면 번역이 잘려 나간다."""
    block = "<!-- projectops:store-notes -->\n**en-US**\n**New**\n- Improved\n**Fixes**\n- Fixed\n<!-- /projectops:store-notes -->\n"
    _, notes = cm.extract_store_notes("본문\n" + block)
    assert list(notes) == ["en-US"]
    assert "Improved" in notes["en-US"] and "Fixed" in notes["en-US"]


def test_language_subtags_with_script_are_accepted():
    block = "<!-- projectops:store-notes -->\n**zh-Hans**\n- 改善\n**vi**\n- Cải thiện\n<!-- /projectops:store-notes -->\n"
    _, notes = cm.extract_store_notes(block)
    assert set(notes) == {"zh-Hans", "vi"}


# ── 이미 준비된 언어별 파일은 기본 문구로 덮지 않는다 ───────────────────
def test_play_keeps_existing_language_file_when_no_translation(tmp_path):
    """레포가 직접 쓴 en-US 노트(다른 스크립트가 먼저 배치)가 있으면, 번역이 없다고 한국어로 덮으면 회귀다."""
    ws = _ws(tmp_path)
    base = ws / "android/fastlane/metadata/android"
    for loc, text in (("en-US", "Hand-written English"), ("ja-JP", "")):
        d = base / loc / "changelogs"
        d.mkdir(parents=True)
        (d / "7.txt").write_text(text, encoding="utf-8")
    out = _run("write", "--platform", "play", "--workspace", ws, "--version", "1", "--version-code", "7",
               "--default-file", ws / "default.txt")
    assert (base / "en-US/changelogs/7.txt").read_text(encoding="utf-8") == "Hand-written English"
    # 비어 있던 ja-JP, 아예 없던 zh-CN 은 기본 문구로 채운다 (빈 언어를 두지 않는다)
    assert (base / "ja-JP/changelogs/7.txt").read_text(encoding="utf-8").strip() == KO
    assert (base / "zh-CN/changelogs/7.txt").read_text(encoding="utf-8").strip() == KO
    assert out["kept"] == ["en-US"] and out["fell_back"] == ["ja-JP", "zh-CN"]


def test_translation_still_wins_over_existing_file(tmp_path):
    ws = _ws(tmp_path, changelog={"releases": [{"version": "1", "store_notes": {"en-US": "- Translated"}}]})
    d = ws / "android/fastlane/metadata/android/en-US/changelogs"
    d.mkdir(parents=True)
    (d / "7.txt").write_text(KO, encoding="utf-8")   # 다른 스크립트가 한국어를 복사해 둔 상태
    _run("write", "--platform", "play", "--workspace", ws, "--version", "1", "--version-code", "7",
         "--default-file", ws / "default.txt")
    assert (d / "7.txt").read_text(encoding="utf-8").strip() == "- Translated"


# ── 스토어마다 언어 구성이 다를 때 ──────────────────────────────────
PER_STORE_YML = '''options:
  store_locales: ["ko-KR", "en-US", "ja-JP", "zh-CN"]
  store_locales_ios: ["ko-KR", "en-US"]
  store_locales_play: ["ko-KR", "en-US", "ja-JP"]
'''


def test_per_store_list_wins_over_common():
    assert sn.read_store_locales(PER_STORE_YML, "ios") == ["ko-KR", "en-US"]
    assert sn.read_store_locales(PER_STORE_YML, "play") == ["ko-KR", "en-US", "ja-JP"]
    # 플랫폼을 안 주면 공통 목록
    assert sn.read_store_locales(PER_STORE_YML) == ["ko-KR", "en-US", "ja-JP", "zh-CN"]


def test_store_without_own_list_falls_back_to_common():
    yml = 'options:\n  store_locales: ["ko-KR", "en-US", "ja-JP"]\n  store_locales_ios: ["ko-KR"]\n'
    assert sn.read_store_locales(yml, "ios") == ["ko-KR"]
    assert sn.read_store_locales(yml, "play") == ["ko-KR", "en-US", "ja-JP"]   # play 키 없음 -> 공통


def test_store_specific_key_alone_enables_that_store_only():
    """공통 키 없이 한 스토어 키만 있어도 그 스토어는 켜지고, 다른 스토어는 옛 동작이다."""
    yml = 'options:\n  store_locales_play: ["ko-KR", "en-US"]\n'
    assert sn.read_store_locales(yml, "play") == ["ko-KR", "en-US"]
    assert sn.read_store_locales(yml, "ios") == []


def test_empty_per_store_list_means_use_common():
    yml = 'options:\n  store_locales: ["ko-KR", "en-US"]\n  store_locales_ios: []\n'
    assert sn.read_store_locales(yml, "ios") == ["ko-KR", "en-US"]


def test_ios_writes_only_its_languages_never_extra(tmp_path):
    """App Store 에 없는 언어(ja/zh-Hans)를 만들면 deliver 가 앱에 그 언어를 새로 활성화한다."""
    ws = _ws(tmp_path, yml=PER_STORE_YML)
    out_dir = tmp_path / "o"
    _run("write", "--platform", "ios", "--workspace", ws, "--version", "1", "--out-dir", out_dir, "--default-file", ws / "default.txt")
    assert sorted(p.name for p in out_dir.iterdir()) == ["en-US.txt", "ko.txt"]


def test_play_writes_only_its_languages_and_prunes_the_rest(tmp_path):
    ws = _ws(tmp_path, yml=PER_STORE_YML)
    stale = ws / "android/fastlane/metadata/android/zh-CN/changelogs"
    stale.mkdir(parents=True)
    (stale / "9.txt").write_text("남은 중국어", encoding="utf-8")
    out = _run("write", "--platform", "play", "--workspace", ws, "--version", "1", "--version-code", "9", "--default-file", ws / "default.txt")
    base = ws / "android/fastlane/metadata/android"
    assert sorted(p.name for p in base.iterdir()) == ["en-US", "ja-JP", "ko-KR", "zh-CN"]   # zh-CN 폴더는 남되
    assert not (stale / "9.txt").exists() and out["pruned"] == ["zh-CN"]                      # 이번 노트는 치웠다
    assert (base / "ja-JP/changelogs/9.txt").is_file()


def test_locales_command_reports_per_store(tmp_path):
    ws = _ws(tmp_path, yml=PER_STORE_YML)
    ios = _run("locales", "--platform", "ios", "--workspace", ws)
    play = _run("locales", "--platform", "play", "--workspace", ws)
    assert [l["code"] for l in ios["locales"]] == ["ko", "en-US"]
    assert [l["code"] for l in play["locales"]] == ["ko-KR", "en-US", "ja-JP"]
