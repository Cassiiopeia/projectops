"""워크플로가 부르는 fastlane lane 이 실재하는가 (#601).

실사고: iOS 테스트 빌드가 **TestFlight 업로드 직전에 항상** 죽었다.

    [!] Could not find lane 'ios upload_testflight'. Available lanes: ios deploy

IPA 는 정상적으로 만들어지고 릴리즈 노트도 생성된 뒤 **마지막 한 스텝에서만** 실패했다.
즉 이 템플릿을 쓰는 레포는 **iOS 테스트 빌드가 한 번도 TestFlight 에 올라간 적이 없다.**

왜 오래 남았나 — 배포 경로(`deploy`)는 맞는 lane 을 불러 멀쩡했고, **테스트 경로만**
틀렸는데 그 경로를 끝까지 밟아본 사람이 없었다. 게다가 앞선 두 버그(#595 권한,
#597 셸 문법)가 이 자리를 가리고 있어 여기까지 오지도 못했다.

같은 종류를 찾아보니 Android 쪽도 둘이나 있었다 — `fastlane build` 를 부르는데
마법사가 까는 Fastfile 에는 `build` lane 이 없다.

**Fastfile 은 마법사가 덮어쓴다.** lane 을 손으로 더하면 다시 깔 때 사라지므로,
워크플로를 있는 lane 에 맞추는 것이 옳다. 이 테스트가 그 정합성을 지킨다.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"
UTIL = ROOT / ".github" / "util"

# `bundle exec fastlane <lane>` / `fastlane <lane>` — 옵션(-)과 하위명령은 제외
_CALL = re.compile(r"(?:bundle\s+exec\s+)?fastlane\s+([a-z][a-z0-9_]*)", re.I)
# fastlane 자체의 하위명령. lane 이 아니다.
_NOT_LANE = {"init", "lanes", "run", "action", "actions", "env", "update",
             "install_plugins", "add_plugin", "match", "gym", "pilot", "deliver",
             "supply", "scan", "snapshot", "sigh", "cert", "produce", "version"}


def _defined_lanes() -> set[str]:
    """마법사 Fastfile 템플릿이 정의하는 lane 전부."""
    lanes: set[str] = set()
    for f in UTIL.rglob("Fastfile*"):
        for m in re.finditer(r"^\s*lane\s*:([a-z0-9_]+)", f.read_text(encoding="utf-8"), re.M):
            lanes.add(m.group(1))
    return lanes


def _called() -> list[tuple[Path, str, str]]:
    """(워크플로, lane, 그 줄) — 워크플로가 부르는 lane."""
    out = []
    for f in sorted(list(WF.rglob("*.yaml")) + list(WF.rglob("*.yml"))):
        for line in f.read_text(encoding="utf-8").splitlines():
            if "fastlane" not in line or line.lstrip().startswith("#"):
                continue
            for m in _CALL.finditer(line):
                lane = m.group(1)
                if lane in _NOT_LANE or lane.startswith("-"):
                    continue
                out.append((f, lane, line.strip()))
    return out


CALLS = _called()


def test_fastfile_templates_exist():
    """템플릿을 못 찾으면 이 테스트는 조용히 아무것도 검사하지 않는다."""
    assert _defined_lanes(), "Fastfile 템플릿에서 lane 을 하나도 찾지 못했다"


@pytest.mark.parametrize(
    "path,lane,line", CALLS,
    ids=[f"{p.name}:{l}" for p, l, _ in CALLS] or ["none"])
def test_called_lane_exists_or_is_guarded(path, lane, line):
    """부르는 lane 이 템플릿에 없으면, **있는지 확인하고 부르는지** 봐야 한다.

    직접 만든 Fastfile 에만 있는 lane 을 쓸 수도 있다. 그 경우는 존재를 확인하고
    없으면 다른 길로 가야 한다 — 무턱대고 부르면 "Could not find lane" 으로 죽는다.
    """
    if lane in _defined_lanes():
        return
    body = path.read_text(encoding="utf-8")
    guarded = re.search(rf"grep[^\n]*lane[^\n]*:{re.escape(lane)}", body)
    assert guarded, (
        f"{path.relative_to(WF)} 가 `fastlane {lane}` 을 부르는데 마법사 Fastfile 에 "
        f"그 lane 이 없다 (있는 것: {', '.join(sorted(_defined_lanes()))}).\n"
        f"  {line}\n"
        "있는 lane 으로 바꾸거나, Fastfile 에 그 lane 이 있는지 확인한 뒤 부르도록 고쳐라."
    )


def test_test_build_pins_deploy_mode():
    """테스트 빌드가 심사 자동 제출까지 가지 않도록 못을 박았는가.

    `deploy` lane 은 DEPLOY_MODE 에 따라 `submit_for_review` 까지 간다. 테스트 빌드가
    기본값에 기대고 있으면, Fastfile 기본값이 바뀌는 순간 **테스트 빌드가 앱 심사에
    제출된다.** 되돌릴 수 없는 종류의 사고다.
    """
    f = WF / "project-types/flutter/PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml"
    body = f.read_text(encoding="utf-8")
    assert "fastlane deploy" in body, "이 테스트가 보는 호출이 바뀌었다 — 함께 고칠 것"
    m = re.search(r'DEPLOY_MODE="([^"]+)"', body)
    assert m, "테스트 빌드가 DEPLOY_MODE 를 명시하지 않는다 — 기본값에 기대면 안 된다"
    assert m.group(1) in ("store_only", "testflight_only"), (
        f"테스트 빌드의 DEPLOY_MODE 가 '{m.group(1)}' 이다 — 심사에 제출될 수 있다")
