"""desktop 명령 (#985) — OS 없이 도는 판단 규칙과 상태 기록."""
from __future__ import annotations

import time

import desktop_input
import pytest

from pro_launch.commands.desktop.common import listed_nodes
from pro_launch.commands.desktop.input_ops import mutating_refusal
from pro_launch.runtime import desktop_state
from pro_launch.runtime.mutating import is_mutating_label


def _node(**kw):
    base = dict(text="Next", id_="btn", desc="", role="button", enabled=True, secret=False,
                actions=["invoke"], bounds=(10, 10, 50, 30), window="Setup")
    base.update(kw)
    return desktop_input.make_desktop_node(**base)


def test_zero_size_or_missing_bounds_is_not_a_node():
    # 깨지면: 보이지 않는 요소를 ref 로 내놓아 눌러도 아무 일이 없다
    assert _node(bounds=(10, 10, 10, 30)) is None
    assert _node(bounds=None) is None
    assert _node()["center"] == [30, 20]


def test_unknown_action_names_are_dropped():
    # 깨지면: 백엔드가 모르는 동작을 시도해 엉뚱한 실패가 난다
    assert _node(actions=["invoke", "scroll"])["actions"] == ["invoke"]


@pytest.mark.parametrize("label, blocked", [
    ("Install", True), ("설치", True), ("동의합니다", True), ("I Agree", True), ("Finish", True),
    ("Next", False), ("다음", False), ("Cancel", False), ("Back", False),
])
def test_desktop_blocks_install_and_agree_but_not_next(label, blocked):
    # 깨지면: 설치 버튼이 승인 없이 눌리거나, 마법사의 "다음"까지 막혀 아무것도 못 한다
    assert is_mutating_label(label, is_desktop=True) is blocked


def test_web_rule_is_unchanged_by_desktop_words():
    # 깨지면: web 읽기 전용 세션이 "설치"류 링크·버튼까지 막는다 (web 동작이 바뀐다)
    assert is_mutating_label("Install", is_desktop=False) is False
    assert is_mutating_label("Delete", is_desktop=False) is True


def test_listed_nodes_marks_only_clickable_mutating():
    nodes = listed_nodes([_node(text="Install"), _node(text="Install guide", role="text", actions=[])])
    # 깨지면: 설명 문구(text)까지 위험 표시가 붙어 agent 가 엉뚱하게 승인을 묻는다
    assert [n["mutating"] for n in nodes] == [True, False]


def test_mutating_and_disabled_refusals():
    node = {**listed_nodes([_node(text="Install")])[0], "ref": 3}
    # 깨지면: 승인 없이 설치가 진행된다
    assert mutating_refusal(node, is_confirmed=False)["code"] == "mutating_blocked"
    assert mutating_refusal(node, is_confirmed=True) is None
    disabled = {**listed_nodes([_node(enabled=False)])[0], "ref": 1}
    assert mutating_refusal(disabled, is_confirmed=False)["code"] == "element_disabled"


def test_locator_compares_role_and_name_not_position():
    saved = {"role": "button", "text": "Next", "id": "a", "bounds": [0, 0, 1, 1]}
    # 깨지면: 창을 옮기기만 해도 ref_stale, 또는 다른 버튼으로 바뀐 화면에서 그대로 누른다
    assert desktop_input.locator_matches(saved, {**saved, "bounds": [5, 5, 9, 9]})
    assert not desktop_input.locator_matches(saved, {**saved, "text": "Install"})
    assert not desktop_input.locator_matches(saved, {**saved, "role": "checkbox"})
    unnamed = {"role": "edit", "text": "", "id": "nameBox"}
    assert desktop_input.locator_matches(unnamed, dict(unnamed))
    assert not desktop_input.locator_matches(unnamed, {**unnamed, "id": "pwBox"})


def test_ratio_point_is_inside_the_window():
    # 깨지면: --at 이 창 밖(다른 앱)을 누른다
    assert desktop_input.ratio_point([100, 200, 300, 400], 0.5, 0.5) == (200, 300)
    assert desktop_input.ratio_point([-1000, 0, 0, 1000], 1.0, 0.0) == (0, 0)


@pytest.mark.parametrize("last, now, moved", [
    (None, (5, 5), False), ([100, 100], (102, 101), False), ([100, 100], (140, 100), True),
])
def test_cursor_drift_detects_the_user(last, now, moved):
    # 깨지면: 사용자가 마우스를 쓰는 중에 클릭이 끼어든다 (또는 떨림만으로 멈춘다)
    assert desktop_input.cursor_moved_by_user(last, now) is moved


def test_absolute_coords_cover_negative_monitors():
    if desktop_input.platform_key() != "windows":
        pytest.skip("windows_input loads user32 — Windows only")
    from desktop_backends import windows_input
    # 깨지면: 왼쪽(음수 좌표) 모니터의 버튼을 누르면 엉뚱한 곳이 눌린다
    assert windows_input.absolute_coords(-1080, 0, (-1080, 0, 3640, 1440)) == (0, 0)
    assert windows_input.absolute_coords(2559, 1439, (-1080, 0, 3640, 1440)) == (65535, 65535)


def test_only_one_session_holds_the_input(monkeypatch):
    monkeypatch.setenv("LAUNCH_SESSION", "session-a")
    assert desktop_state.start_session("first")[0]
    monkeypatch.setenv("LAUNCH_SESSION", "session-b")
    got, holder = desktop_state.start_session("second")
    # 깨지면: 두 agent 가 같은 마우스·키보드를 두고 싸운다
    assert not got and holder["session"] == "session-a"
    assert desktop_state.stop_session() is False   # 남의 세션은 못 푼다
    monkeypatch.setenv("LAUNCH_SESSION", "session-a")
    assert desktop_state.stop_session() is True


def test_idle_session_expires(monkeypatch):
    monkeypatch.setenv("LAUNCH_SESSION", "session-a")
    desktop_state.start_session("old", now=time.time() - desktop_state.SESSION_IDLE_SECONDS - 5)
    # 깨지면: 끝내지 않고 떠난 세션이 마우스를 계속 쥐고 있어 다른 세션이 영영 못 쓴다
    assert desktop_state.current_holder() is None


def test_snapshot_is_per_session(monkeypatch):
    monkeypatch.setenv("LAUNCH_SESSION", "session-a")
    desktop_state.save_snapshot({"handle": 1}, [{"ref": 1, "text": "Next"}])
    monkeypatch.setenv("LAUNCH_SESSION", "session-b")
    # 깨지면: 다른 세션의 find 번호로 눌러 엉뚱한 버튼을 누른다
    assert desktop_state.load_snapshot() == {}


def test_every_registered_backend_implements_the_contract():
    required = ("missing_modules", "readiness", "windows", "nodes", "focus", "perform",
                "cursor", "mouse_click", "type_text", "press", "grab")
    for key, target in desktop_input.BACKENDS.items():
        module_name, class_name = target.split(":")
        if desktop_input.platform_key() != key:
            continue   # 다른 OS 백엔드는 그 OS 라이브러리를 가져온다
        cls = getattr(__import__(module_name, fromlist=[class_name]), class_name)
        # 깨지면: 새 OS 백엔드가 필수 동작을 빠뜨려 그 OS 에서만 실행 중 터진다
        assert cls.name == key and cls.packages and cls.install_hint
        for method in required:
            assert getattr(cls, method) is not getattr(desktop_input.DesktopBackend, method), f"{key}.{method}"
