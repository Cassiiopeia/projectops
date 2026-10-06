"""Play Store 워크플로가 넘기는 값을 Fastfile 템플릿이 실제로 읽는가 (#764 #766).

실사고: 사용자가 Fastfile 을 직접 고쳐 비공개 테스트만 올리게 만들자, 워크플로가 넘기는
DEPLOY_MODE 가 **조용히 무시**됐다. 설정이 먹었다고 믿은 채 배포가 중간에서 멈췄다.
템플릿 쪽에서도 같은 어긋남이 생기지 않도록, 워크플로가 fastlane 에 넘기는 환경변수 이름이
모두 템플릿에 나타나는지 지킨다.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github/workflows/project-types/flutter/PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml"
TPL = ROOT / ".github/util/flutter/playstore-wizard/templates/Fastfile.playstore.template"

# 워크플로 step env 중 fastlane 이 읽지 않는 것(인증·경로·번들)은 계약 대상이 아니다.
_PASSED = ["DEPLOY_MODE", "PROMOTE_TO_CLOSED_TESTING", "PROMOTE_TO_OPEN_TESTING",
           "CLOSED_TESTING_TRACK", "OPEN_TESTING_TRACK", "PRODUCTION_ROLLOUT"]


def _upload_step_env() -> str:
    text = WF.read_text(encoding="utf-8")
    start = text.index("- name: Upload to Play Store Internal Testing")
    return text[start:start + 1800]


@pytest.mark.parametrize("name", _PASSED)
def test_워크플로가_넘기는_값을_템플릿이_읽는다(name):
    # DEPLOY_MODE, PRODUCTION_ROLLOUT 은 설정 파일 단계가 GITHUB_ENV 로 덮어쓸 수 있어 step env 로 다시
    # 지정하지 않고 환경변수를 그대로 물려받는다. 그래서 워크플로 최상위 env 에 정의돼 있는지 본다.
    top = WF.read_text(encoding="utf-8").split("\njobs:")[0]
    assert re.search(rf"^  {name}:", top, re.M), f"워크플로가 {name} 을 정의하지 않는다"
    assert re.search(rf'ENV\["{name}"\]', TPL.read_text(encoding="utf-8")), \
        f"템플릿이 {name} 을 읽지 않는다 — 워크플로 설정이 조용히 무시된다"


def test_롤아웃_비율은_범위를_검증하고_기본은_전면_출시다():
    t = TPL.read_text(encoding="utf-8")
    assert '(ENV["PRODUCTION_ROLLOUT"] || "1.0")' in t, "기본값이 바뀌면 기존 동작이 달라진다"
    assert "rollout_value > 0 && rollout_value <= 1" in t
    # 단계적 출시는 inProgress 로 표현된다
    assert "'inProgress'" in t


def test_승급_실패_메시지가_최초_수동_출시_요건을_원인_후보로_든다():
    t = TPL.read_text(encoding="utf-8")
    assert "production: true" in t and "한 번도 출시된 적이 없다면" in t


def test_Fastfile_무시_감지가_복사_단계에_있다():
    w = WF.read_text(encoding="utf-8")
    assert "Fastfile 이 $name 을 읽지 않습니다" in w


@pytest.mark.local_only
@pytest.mark.skipif(shutil.which("ruby") is None, reason="ruby 가 있어야 문법을 검사할 수 있다")
def test_템플릿이_ruby_문법을_통과한다():
    r = subprocess.run(["ruby", "-c", str(TPL)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ── #765 프로덕션 출시 이력 사전 확인 ────────────────────────────────

def test_프로덕션_승급_전에_출시_이력을_미리_확인한다():
    t = TPL.read_text(encoding="utf-8")
    assert "google_play_track_version_codes" in t, "프로덕션 트랙 이력 조회가 없다"
    # 승급(Step 3)보다 앞에서 확인해야 실패하기 전에 알릴 수 있다
    assert t.index("google_play_track_version_codes") < t.index("promote_internal_to_production(promote_status")


def test_이력_조회_실패는_배포를_막지_않고_경고만_한다():
    t = TPL.read_text(encoding="utf-8")
    block = t[t.index("def warn_if_never_released"):]
    block = block[:block.index("\nend\n")]
    assert "rescue StandardError" in block, "조회 실패가 배포를 죽이면 안 된다 (권한 없음 등)"
    assert "::warning" in block, "경고는 CI 실행 목록에 떠야 한다"
    assert "raise" not in block, "사전 확인은 막지 않는다 (실제로 승급이 안 되는지는 콘솔만 안다)"
