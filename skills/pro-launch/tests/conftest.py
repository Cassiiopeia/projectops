"""pro-launch 테스트 공통 — 실제 ~/.projectops 를 건드리지 않는다 (#836).

브라우저 테스트는 HOME 을 바꿀 수 없다(macOS Chrome 이 멈춘다, 실측). 그대로 두면 실제 홈에
`acme__thing`·`webproj` 같은 버킷이 생기고 실제 기억의 memory_seen.json 까지 건드린다.
HOME 은 그대로 두고 상태 루트(PROJECTOPS_HOME)만 테스트마다 임시 폴더로 돌린다.

경로를 `tmp_path/home/.projectops` 로 두는 이유: HOME 을 `tmp_path/home` 으로 바꾸는 기존
테스트의 기대 경로와 그대로 맞는다.
"""
import warnings

import pytest

from browser_cleanup import sweep_browsers_under


@pytest.fixture(autouse=True)
def _isolated_projectops_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / ".projectops"
    monkeypatch.setenv("PROJECTOPS_HOME", str(home))
    return home


@pytest.fixture(autouse=True)
def _no_real_maestro_processes(monkeypatch):
    """실제 ps 로 이 컴퓨터의 Maestro 드라이버를 보거나 끝내지 않는다 (#922) · 부하로 켜진 환경변수가 새지 않게 한다."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    import maestro_drivers
    monkeypatch.setattr(maestro_drivers, "list_processes", lambda: [])
    monkeypatch.setattr(maestro_drivers, "CLEANED_DRIVERS", [])
    monkeypatch.delenv("MAESTRO_DRIVER_STARTUP_TIMEOUT", raising=False)


@pytest.fixture(scope="session", autouse=True)
def _no_browser_left_behind(tmp_path_factory):
    """세션이 끝나면 이 pytest 의 임시 폴더 아래 프로필로 남은 브라우저를 끈다 (#921).

    fixture 정리(close_browser_for_test)가 놓친 것의 안전망 — 부모 없는 headless Chrome 이 쌓이면 사용자 Chrome 이 막힌다.
    """
    yield
    left = sweep_browsers_under(tmp_path_factory.getbasetemp())
    if left:
        warnings.warn(f"테스트가 브라우저를 남겼다 (세션 끝에 정리함): pid {left}")


# ── 실제 홈 보호 (#932) ───────────────────────────────────────────────────
#
# 위 fixture 가 PROJECTOPS_HOME 을 돌린다. 어떤 테스트가 그것을 지우거나 실제 ~/.projectops 로
# 되돌려 실제 기억·버킷을 오염시키면 그 테스트를 실패시킨다 (server.zz-verify.* 유출의 재발 방지).
import os  # noqa: E402
from pathlib import Path  # noqa: E402

# 테스트가 HOME 을 바꾸기 전, 모듈을 읽는 시점의 실제 상태 루트
REAL_PROJECTOPS_HOME = Path.home() / ".projectops"


@pytest.fixture(autouse=True)
def _guard_real_projectops_home(_isolated_projectops_home):
    yield
    configured = os.environ.get("PROJECTOPS_HOME")
    # 비어 있으면 테스트가 일부러 지운 것(탈출구 검증)이다 — 실제 홈으로 돌린 경우만 막는다
    assert not configured or Path(configured).expanduser().resolve() != REAL_PROJECTOPS_HOME.resolve(), \
        "테스트가 PROJECTOPS_HOME 을 실제 ~/.projectops 로 돌렸다"


@pytest.fixture(scope="session", autouse=True)
def _real_machine_knowledge_untouched():
    """세션 전후로 실제 이 컴퓨터 기억 파일이 그대로인지 본다 (테스트 유출 감지, #932)."""
    target = REAL_PROJECTOPS_HOME / "launch" / "_machine" / "knowledge.json"
    before = target.read_bytes() if target.is_file() else None
    yield
    after = target.read_bytes() if target.is_file() else None
    assert before == after, "테스트가 실제 ~/.projectops/launch/_machine/knowledge.json 을 바꿨다"


@pytest.fixture(autouse=True)
def _no_real_device_key_lookup(monkeypatch):
    """원장 키를 얻으려고 실제 adb 에 묻지 않는다 · 이 프로세스의 호스트 판별 캐시를 테스트마다 비운다 (#953)."""
    from pro_launch.runtime import device_claims
    monkeypatch.setattr(device_claims, "resolve_instance_key", lambda dev_id: dev_id)
    monkeypatch.setattr(device_claims, "_CURRENT_HOST", {})
    monkeypatch.setattr(device_claims, "_KEY_BY_INSTANCE", {})
