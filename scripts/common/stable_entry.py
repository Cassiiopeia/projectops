"""고정 진입점 설치와 옛 버전 경고 (#942).

run_cli 가 매 실행 부른다. 깔린 번호만 읽고 비교하므로 가볍고, 실패해도 명령을 막지 않는다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
# 한 프로세스에서 경고를 한 번만 싣는다
_warned = False


def _projectops_home() -> Path:
    return Path(os.environ.get("PROJECTOPS_HOME") or Path.home() / ".projectops")


def _load_resolver():
    if str(_SCRIPTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_ROOT))
    import projectops_cli
    return projectops_cli


def refresh_and_check(running_cli_path: str) -> Optional[dict]:
    """고정 진입점을 최신으로 맞추고, 캐시의 옛 버전에서 돌고 있으면 {running, installed, use}. 아니면 None"""
    global _warned
    # 테스트가 실제 홈의 ~/.projectops/bin 을 건드리지 않게 한다
    if "PYTEST_CURRENT_TEST" in os.environ:
        return None
    try:
        resolver = _load_resolver()
        resolver.refresh_stable_entrypoint(_projectops_home())
        running_dir = Path(running_cli_path).resolve().parent
        skill = next((name for name, (folder, cli) in resolver.SKILL_CLIS.items()
                      if running_dir.parent.name == folder and running_dir.name == "scripts"), None)
        if skill is None or _warned:
            return None
        info = resolver.newer_installed_info(running_dir, skill)
        _warned = info is not None
        return info
    except Exception:  # 진입점 갱신 실패가 명령을 막으면 안 된다
        return None
