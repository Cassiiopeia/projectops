"""빌드 트리거의 payload build_number 호환 계약 (#643).

마법사는 사용자가 수정한 워크플로를 덮어쓰지 않고 남겨 둔다(skipped-conflict).
그래서 트리거는 새 것인데 빌더는 옛 수정본인 저장소가 생긴다. 옛 빌더는 payload 의
build_number 를 그대로 빌드 번호로 쓰므로(iOS 는 --build-number, Android 는 pubspec 의 +N),
트리거가 빈 값을 보내면 그 저장소의 테스트 빌드가 깨진다.
새 빌더는 이 값을 읽지 않으니, 옛 빌더가 있는 동안은 번호 계산이 트리거에 남아 있어야 한다.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
TRIGGER = ROOT / ".github/workflows/project-types/flutter/PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml"


def _steps():
    doc = yaml.safe_load(TRIGGER.read_text(encoding="utf-8"))
    return [s for job in doc["jobs"].values() for s in job["steps"]]


def test_trigger_still_computes_legacy_build_number():
    ids = [s.get("id") for s in _steps()]
    assert "build_number_calc" in ids, "옛 빌더 호환용 번호 계산을 지우면 수정본 빌더가 있는 저장소의 빌드가 깨진다"


def test_dispatch_payload_never_sends_empty_build_number():
    text = TRIGGER.read_text(encoding="utf-8")
    # dispatch 두 곳 모두 계산 결과를 그대로 보낸다
    assert len(re.findall(r"steps\.build_number_calc\.outputs\.buildNumber", text)) >= 2
    assert not re.search(r"const buildNumber = '';", text), "빈 번호를 보내면 옛 빌더가 깨진다"
    assert text.count("build_number: buildNumber") == 2
