#!/usr/bin/env python3
"""figma_cli — 시안과 구현 화면을 대조한다 (projectops 3-layer Layer 2).

**눈으로는 못 잡는다.** 어떤 버튼에서 효과 네 줄 중 안쪽 세 줄이 통째로 빠진 채
배포된 일이 있었다. 전체 화면 골든을 만들어 놓고도 지나갔다 — 361x68 안의 10px
안쪽 그림자는 그 크기에서 몇 픽셀이라 있으나 없으나 비슷해 보인다.

값 단언(`expect(shadow.blur, 10)`)도 절반만 막는다. **단언하기로 생각한 것만**
지킨다. 빠뜨린 줄은 애초에 단언도 안 썼으니 아무도 세지 않는다.

그래서 두 가지를 한다.

  coverage — 덤프의 스타일 항목을 **하나도 빠짐없이 나열**해 분류를 강제한다.
             값을 못 옮긴 것과 안 옮기기로 한 것을 구분하는 것이 요점이다.
  diff     — 그림으로 맞대 어디가 다른지 덩어리로 뽑는다.

판단은 사람이 한다. 이 스크립트는 **세고 나열하고 그릴 뿐**이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))
# 구현 패키지(figma_tools)는 이 파일 옆에 있다 — 설치 위치와 무관하게 진입 파일 기준으로 찾는다
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from figma_tools.cli import build_parser, main  # noqa: E402,F401
from figma_tools.commands.assets import cmd_assets  # noqa: E402,F401
from figma_tools.commands.conform import cmd_conform  # noqa: E402,F401
from figma_tools.commands.coverage import cmd_coverage  # noqa: E402,F401
from figma_tools.commands.diff import cmd_diff  # noqa: E402,F401
from figma_tools.commands.output_path import cmd_output_path  # noqa: E402,F401
from figma_tools.commands.store import cmd_store_check, cmd_store_specs  # noqa: E402,F401
# 순수 값 검사 테스트가 진입 모듈에서 바로 읽는 이름
from figma_tools.conform_probes import (  # noqa: E402,F401
    _CORNER_LIMIT, _CORNER_PROBE, _fill_kind, _parse_radius, _shadow_offsets,
)


if __name__ == "__main__":
    sys.exit(main())
