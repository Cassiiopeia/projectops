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


# ── 배포 기본값은 안전한 쪽이어야 한다 (#618) ────────────────────────────
#
# 실사고 직전까지 갔던 것: Android Fastfile 의 내부 기본값이 `store_submit` 이라,
# 워크플로를 거치지 않고 `fastlane deploy_internal` 을 직접 부르면 **프로덕션 심사에
# 자동 등록**됐다. 워크플로 기본값은 `store_only` 였으니 두 기본값이 반대였다.
# iOS 쪽은 `testflight_only` 로 안전했고 Android 만 그랬다.
#
# #601 이 같은 종류를 경고한다 — "기본값에 기대고 있으면 Fastfile 기본값이 바뀌는
# 순간 테스트 빌드가 앱 심사에 올라간다. 되돌릴 수 없는 종류의 사고다."

# 심사·출시로 이어지는 값. 기본값으로 쓰여선 안 된다.
_UNSAFE_DEFAULTS = {"store_submit", "store_prepare", "appstore_submit", "appstore_prepare"}
_ENV_DEFAULT = re.compile(r'ENV\["DEPLOY_MODE"\]\s*\|\|\s*"([a-z_]+)"')


def _fastfile_defaults():
    """(파일, 기본값) — Fastfile 템플릿이 DEPLOY_MODE 없이 돌 때 쓰는 값."""
    out = []
    for f in sorted(UTIL.rglob("Fastfile*")):
        for m in _ENV_DEFAULT.finditer(f.read_text(encoding="utf-8")):
            out.append((f, m.group(1)))
    return out


def test_fastfile_default_deploy_mode_is_safe():
    """환경변수 없이 lane 을 직접 불러도 심사·출시로 가지 않아야 한다."""
    found = _fastfile_defaults()
    assert found, "DEPLOY_MODE 기본값을 하나도 못 찾았다 — 검사가 헛돌고 있다"
    unsafe = [f"{p.relative_to(ROOT).as_posix()} → {v}"
              for p, v in found if v in _UNSAFE_DEFAULTS]
    assert unsafe == [], (
        "Fastfile 기본값이 심사·출시로 이어진다. 워크플로를 거치지 않고 lane 을 직접\n"
        "부르면 그대로 나간다 — 되돌릴 수 없다:\n" + "\n".join(unsafe))


def test_fastfile_and_workflow_defaults_agree():
    """두 기본값이 어긋나면, 어느 쪽을 보고 판단해도 틀리게 된다."""
    wf_defaults = set()
    for f in sorted(list(WF.rglob("*.yaml")) + list(WF.rglob("*.yml"))):
        for m in re.finditer(r"DEPLOY_MODE:\s*\$\{\{[^}]*\|\|\s*'([a-z_]+)'\s*\}\}",
                             f.read_text(encoding="utf-8")):
            wf_defaults.add(m.group(1))
    if not wf_defaults:
        pytest.skip("워크플로에 DEPLOY_MODE 기본값이 없다")

    ff_defaults = {v for _, v in _fastfile_defaults()}
    # iOS 는 testflight_only, Android 는 store_only — 이름은 달라도 둘 다
    # "스토어 심사로 가지 않는다"는 같은 뜻이다. 위험값이 섞였는지만 본다.
    assert not (ff_defaults & _UNSAFE_DEFAULTS), ff_defaults
    assert not (wf_defaults & _UNSAFE_DEFAULTS), wf_defaults


def test_track_promotion_switches_reach_the_fastfile():
    """워크플로가 스위치를 안 넘기면 Fastfile 기본값(false)만 돌아 승급이 영영 안 된다."""
    play = UTIL / "flutter" / "playstore-wizard" / "templates" / "Fastfile.playstore.template"
    body = play.read_text(encoding="utf-8")
    for key in ("PROMOTE_TO_CLOSED_TESTING", "PROMOTE_TO_OPEN_TESTING",
                "CLOSED_TESTING_TRACK", "OPEN_TESTING_TRACK"):
        assert f'ENV["{key}"]' in body, f"Fastfile 이 {key} 를 읽지 않는다"

    wf = WF / "project-types" / "flutter" / "PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml"
    wf_body = wf.read_text(encoding="utf-8")
    for key in ("PROMOTE_TO_CLOSED_TESTING", "PROMOTE_TO_OPEN_TESTING",
                "CLOSED_TESTING_TRACK", "OPEN_TESTING_TRACK"):
        # 최상위 env 선언 + 스텝 전달, 둘 다 있어야 실제로 닿는다
        assert wf_body.count(key) >= 2, f"워크플로가 {key} 를 Fastfile 까지 넘기지 않는다"


def test_track_names_are_not_hardcoded_in_promotion():
    """콘솔에서 임의 이름의 비공개 트랙을 만들 수 있다 — 박아두면 조용히 안 올라간다."""
    play = UTIL / "flutter" / "playstore-wizard" / "templates" / "Fastfile.playstore.template"
    body = play.read_text(encoding="utf-8")
    assert "track_promote_to: 'alpha'" not in body
    assert "track_promote_to: 'beta'" not in body
