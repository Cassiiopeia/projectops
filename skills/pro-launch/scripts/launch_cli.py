#!/usr/bin/env python3
"""launch_cli — pro-launch 전용 CLI (projectops 3-layer 표준, Layer 2, #629).

앱·웹·서버를 **띄우고, 조작하고, 찍는** 능력만 담는다. 무엇을 왜 찍을지는 부르는
작업 스킬(pro-agent-test · pro-design-brief · pro-figma)이 정한다.

원칙: **판단은 agent, 스크립트는 실행과 기록.** 프로젝트 구조를 알아맞히지 않는다.

서브커맨드:
    doctor           도구 설치 여부 · 저장 위치
    detect           무엇을 띄울 수 있는지 (마커 파일 · 기기 · 브라우저)
    devices          붙은 기기 · 부팅된 시뮬레이터 · AVD
    device           역할을 기기에 묶는다 (list · bind · unbind · show)
    app              앱 화면을 찍고(shot) 띄운다(launch)
    web              브라우저 조작 (setup · open · goto · click · type · shot · assert ·
                     console · close · viewport · route)
    http             단건 HTTP 요청
    access           붙는 법 기록 (show · set · unset)
    db               SQL 실행 (붙는 법은 access 에 적어 둔 대로)
    logs             서버 로그 (보는 법도 access 에 적어 둔 대로)
    shrink           이슈 첨부용 축소 · WebP
    recall · learn · forget   이 컴퓨터에서 먹힌 조작 방식을 기억한다 (쓸수록 정확해진다)
    get-output-path  이번 실행 자리 + env.sh

출력: MCP-style JSON (ok/code/summary/next 4필드 보장).
"""
from __future__ import annotations

import sys
from pathlib import Path

# 이 파일은 진입점일 뿐이다. 구현은 같은 폴더의 pro_launch 패키지에 있다 (지도: pro_launch/ARCHITECTURE.md).
_HERE = Path(__file__).resolve()
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from pro_launch.cli import build_parser, main  # noqa: E402,F401


def _refresh_stable_entrypoint() -> None:
    """~/.projectops/bin/launch_cli.py(버전 무관 진입점) 갱신 + 옛 캐시 버전이면 응답 JSON 에 newer_installed (#897·#920).

    stderr 가 아니라 JSON 에 싣는다 — `2>&1 | json.load` 파이프가 깨지지 않게. 실패해도 명령은 돈다
    """
    try:
        import launch_resolver
        from common.state import base_dir
        from pro_launch.runtime.plugin_version import set_newer_installed
        launch_resolver.refresh_stable_entrypoint(base_dir())
        set_newer_installed(launch_resolver.newer_installed_info(_HERE.parent))
    except Exception:  # noqa: BLE001 — 부가 기능이 본 명령을 막지 않게
        pass


if __name__ == "__main__":
    _refresh_stable_entrypoint()
    sys.exit(main())
