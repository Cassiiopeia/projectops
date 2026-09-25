"""스토어 '새로운 기능' 문구 덮어쓰기와 심사 메모 파일 (#628).

스토어 '새로운 기능(What's New)' 칸은 사용자뿐 아니라 **심사자도 본다.** 레포마다 CHANGELOG 를
그대로 보이고 싶은 곳과 한 줄 고정 문구만 두고 싶은 곳이 갈린다. 그래서 워크플로 env
`STORE_WHATS_NEW_OVERRIDE` 로 덮어쓸 수 있게 했다.

**기본값은 빈 문자열이어야 한다** — 기존 사용자에게 아무것도 바뀌지 않게 하는 약속이다.

결정 규칙은 두 군데에 산다 (iOS 는 Fastfile, Android 는 워크플로 셸). 둘 다 표식 구간을
떼어 실제로 실행해 본다. 문자열 검사만 하면 공백 처리 같은 동작 결함을 못 잡는다.
"""
import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FLUTTER_WF = ROOT / ".github" / "workflows" / "project-types" / "flutter"
IOS_WF = FLUTTER_WF / "PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml"
ANDROID_WF = FLUTTER_WF / "PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml"
IOS_FASTFILE = ROOT / ".github" / "util" / "flutter" / "testflight-wizard" / "templates" / "Fastfile.ios.template"

OVERRIDE = "이번 버전에서 버그를 고치고 성능을 개선했어요."
CHANGELOG = "- 로그인 화면 개선"


def _block(text: str, start: str, end: str) -> str:
    """표식 사이 구간. 표식이 사라지면 테스트가 조용히 비지 않도록 바로 실패한다."""
    # 표식 줄 자체는 한 줄 안에서만 맞춘다 (re.S 아래 .* 는 줄을 넘어가 구간이 비어 버린다)
    m = re.search(rf"^[^\n]*{re.escape(start)}[^\n]*\n(.*?)^[^\n]*{re.escape(end)}", text, re.S | re.M)
    assert m and m.group(1).strip(), f"표식 구간 {start}…{end} 을 찾지 못했다"
    return m.group(1)


# ── 기본값: 기존 사용자에게 변화 없음 ───────────────────────────────

@pytest.mark.parametrize("wf", [IOS_WF, ANDROID_WF], ids=["ios", "android"])
def test_template_default_is_empty(wf):
    assert re.search(r'^  STORE_WHATS_NEW_OVERRIDE: ""\s*$', wf.read_text(encoding="utf-8"), re.M), \
        f"{wf.name}: 템플릿 기본값은 빈 문자열이어야 한다"


@pytest.mark.parametrize("wf", [IOS_WF, ANDROID_WF], ids=["ios", "android"])
def test_input_passed_via_env_not_inline(wf):
    """수동 실행 입력을 run: 본문에 ${{ }} 로 박으면 셸 주입이 된다. step env 로만 받는다."""
    text = wf.read_text(encoding="utf-8")
    assert "INPUT_WHATS_NEW_OVERRIDE: ${{ github.event.inputs.whats_new_override }}" in text
    for line in text.splitlines():
        if "github.event.inputs.whats_new_override" in line:
            assert line.strip().startswith("INPUT_WHATS_NEW_OVERRIDE:"), line


def test_ios_upload_step_receives_override():
    """env 는 fastlane 까지 가야 의미가 있다."""
    text = IOS_WF.read_text(encoding="utf-8")
    assert "STORE_WHATS_NEW_OVERRIDE: ${{ env.STORE_WHATS_NEW_OVERRIDE }}" in text


# ── iOS: Fastfile 의 결정 규칙을 ruby 로 실제 실행 ─────────────────

def _ruby(expr: str, tmp_path: Path) -> str:
    code = _block(IOS_FASTFILE.read_text(encoding="utf-8"), ">>> store-text", "<<< store-text")
    script = tmp_path / "t.rb"
    script.write_text(code + "\n" + expr + "\n", encoding="utf-8")
    out = subprocess.run(["ruby", str(script)], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


needs_ruby = pytest.mark.skipif(shutil.which("ruby") is None, reason="ruby 없음")

CASES = [
    # (override, changelog, 기대 문구, 기대 출처)
    (None, CHANGELOG, CHANGELOG, "CHANGELOG"),
    (None, None, "버그를 수정하고 안정성을 개선했습니다.", "기본 문구"),
    ("   \n ", CHANGELOG, CHANGELOG, "CHANGELOG"),
    ("   ", None, "버그를 수정하고 안정성을 개선했습니다.", "기본 문구"),
    (OVERRIDE, CHANGELOG, OVERRIDE, "STORE_WHATS_NEW_OVERRIDE 덮어쓰기"),
    (OVERRIDE, None, OVERRIDE, "STORE_WHATS_NEW_OVERRIDE 덮어쓰기"),
]


def _rb(v):
    # 파이썬 repr 은 작은따옴표라 ruby 에서 \n 이 이스케이프로 풀리지 않는다 — JSON 문자열은 ruby 큰따옴표와 호환된다
    return "nil" if v is None else json.dumps(v, ensure_ascii=False)


@needs_ruby
@pytest.mark.parametrize("override,changelog,text,source", CASES)
def test_ios_resolve_whats_new(override, changelog, text, source, tmp_path):
    out = _ruby(f"t, s = resolve_whats_new({_rb(override)}, {_rb(changelog)}); puts t; puts s", tmp_path)
    assert out.splitlines() == [text, source]


@needs_ruby
def test_ios_review_notes_from_file(tmp_path):
    """review_notes.txt 가 있으면 그 내용, 없거나 비면 nil — nil 이면 ASC 기존값을 건드리지 않는다."""
    f = tmp_path / "review_notes.txt"
    assert _ruby(f"p resolve_review_notes({str(f)!r})", tmp_path) == "nil"
    f.write_text("  \n", encoding="utf-8")
    assert _ruby(f"p resolve_review_notes({str(f)!r})", tmp_path) == "nil"
    f.write_text("\n'Apple로 계속하기'로 로그인하세요.\n", encoding="utf-8")
    assert _ruby(f"puts resolve_review_notes({str(f)!r})", tmp_path) == "'Apple로 계속하기'로 로그인하세요."


def test_ios_never_writes_empty_review_notes():
    """빈 notes.txt 로 '초기화'하던 옛 방식은 deliver 가 빈 값을 보내지 않아 동작하지 않았다 (실측)."""
    text = IOS_FASTFILE.read_text(encoding="utf-8")
    assert 'File.write(File.join(review_dir, "notes.txt"), "")' not in text


# ── Android: 워크플로 셸 구간을 bash 로 실제 실행 ──────────────────

def _android(tmp_path: Path, override, changelog, input_override=None):
    body = textwrap.dedent(_block(ANDROID_WF.read_text(encoding="utf-8"), ">>> whats-new", "<<< whats-new"))
    notes = tmp_path / "final_release_notes.txt"
    if changelog is not None:
        notes.write_text(changelog + "\n", encoding="utf-8")
    env = {**os.environ, "GITHUB_WORKSPACE": str(tmp_path),
           "STORE_WHATS_NEW_OVERRIDE": override or "",
           "INPUT_WHATS_NEW_OVERRIDE": input_override or ""}
    out = subprocess.run(["bash", "-c", "set -e\n" + body], env=env,
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    got = notes.read_text(encoding="utf-8").strip() if notes.exists() else None
    return got, out.stdout


@pytest.mark.parametrize("override,changelog,text,source", CASES)
def test_android_release_notes_source(override, changelog, text, source, tmp_path):
    got, log = _android(tmp_path, override, changelog)
    if source == "STORE_WHATS_NEW_OVERRIDE 덮어쓰기":
        assert got == OVERRIDE
        assert "출처: STORE_WHATS_NEW_OVERRIDE 덮어쓰기" in log
    else:
        # 덮어쓰지 않으면 CHANGELOG 파일을 그대로 둔다 (없으면 뒤 단계가 기본 문구를 만든다)
        assert got == changelog
        assert "출처: CHANGELOG" in log


def test_android_dispatch_input_wins(tmp_path):
    got, _ = _android(tmp_path, OVERRIDE, CHANGELOG, input_override="이번만 쓰는 문구")
    assert got == "이번만 쓰는 문구"
