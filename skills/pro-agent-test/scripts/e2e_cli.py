#!/usr/bin/env python3
"""e2e_cli — pro-agent-test 전용 CLI (projectops 3-layer 표준, Layer 2).

**QA 절차만** 담는다. 앱·웹·서버를 띄우고 조작하고 찍는 능력은 pro-launch 로 옮겼다 (#629·#631).

서브커맨드:
    detect    무엇을 밟을 수 있는지 — pro-launch detect 결과 + 확인해 적어 둔 타겟(note target)
    scenario  밟기 시나리오 만들기 · 목록 · 검증
    note      이 프로젝트에서 알아낸 것을 쌓는다
    api       서버 시나리오를 끝까지 밟는다 (단건 요청은 pro-launch http)
    other     앱·웹·서버가 아닌 것을 밟는다

옮긴 명령(doctor · devices · device · web · access · db · logs · shrink · get-output-path)은
**한 마이너 버전 동안** pro-launch 로 그대로 넘겨주고, 결과에 새 자리를 알리는 next 를 싣는다.

출력: MCP-style JSON (ok/code/summary/next 4필드 보장).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 구현은 같은 폴더의 pro_agent_test 패키지에 있다 (공용 common 경로는 패키지가 맞춘다)
_HERE = Path(__file__).resolve()
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

import pro_agent_test  # noqa: E402,F401  (common import 경로를 맞춘다)
from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402

from pro_agent_test.commands.api import cmd_api  # noqa: E402
from pro_agent_test.commands.detect import cmd_detect  # noqa: E402
from pro_agent_test.commands.note import cmd_note  # noqa: E402
from pro_agent_test.commands.other import cmd_other  # noqa: E402
from pro_agent_test.commands.scenario import cmd_scenario  # noqa: E402
from pro_agent_test.launch_bridge import MOVED, delegate  # noqa: E402
from pro_agent_test.scenario_rules import DEFAULT_TARGET, TARGETS  # noqa: E402

# 테스트가 e2e_cli.<이름> 으로 직접 쓰는 내부 함수 재노출
from common import memory as _memory  # noqa: E402,F401
from common.access import find_secrets as _find_secrets  # noqa: E402,F401
from pro_agent_test.commands.api import _fill, _jsonpath, _parse_do  # noqa: E402,F401
from pro_agent_test.notes.store import _promote_screen  # noqa: E402,F401
from pro_agent_test.scenario_rules import _validate, scenario_target  # noqa: E402,F401
from pro_agent_test.storage import _expand, _home_dir, _repo_key, _resolve_scenario  # noqa: E402,F401


def build_parser() -> JSONArgumentParser:
    # 인자 오류도 JSON(bad_args)으로 — 에이전트는 stdout JSON 만 읽는다 (#708)
    parser = JSONArgumentParser(
        prog="e2e_cli",
        description="agent QA — 앱·웹·서버를 밟아 버그를 찾는다 (실행·캡처는 pro-launch)",
        epilog=("옮긴 명령: " + " · ".join(MOVED)
                + " — pro-launch 의 launch_cli.py 로 넘겨준다 (다음 마이너에서 제거)"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_d = sub.add_parser("detect", help="무엇을 밟을 수 있는지 (pro-launch detect + note target)")
    p_d.add_argument("--path", default=".", help="탐색 시작 경로 (기본: 현재 디렉터리)")
    p_d.add_argument("--target", default=None,
                     help=f"밟을 대상을 직접 지정 ({'·'.join(TARGETS)}). 생략하면 감지한다")
    p_d.set_defaults(func=cmd_detect)

    p_sc = sub.add_parser("scenario", help="프로젝트별 밟기 시나리오 관리")
    p_sc.add_argument("action", choices=["init", "list", "show"])
    p_sc.add_argument("--target", default=DEFAULT_TARGET,
                      help=f"무엇으로 조작하나 ({'·'.join(TARGETS)}, 기본 {DEFAULT_TARGET})")
    p_sc.add_argument("--name", help="시나리오 파일 이름 (확장자 제외)")
    p_sc.add_argument("--root", default=".", help="프로젝트 루트")
    p_sc.add_argument("--group",
                      help="init: flows/{그룹}/ 아래에 만든다. _shared 면 전제로 둔다")
    p_sc.add_argument("--force", action="store_true", help="init 시 덮어쓰기")
    p_sc.set_defaults(func=cmd_scenario)

    p_n = sub.add_parser("note", help="이 프로젝트에서 알아낸 것을 쌓는다")
    p_n.add_argument("action",
                     choices=["show", "target", "constraint", "screen", "pitfall", "run",
                              "tidy", "forget"])
    p_n.add_argument("--root", default=".")
    p_n.add_argument("--name", help="screen: 화면 이름 / run: 시나리오 이름")
    p_n.add_argument("--anchor", help="screen: 이 화면임을 알아보는 단서(문구 등). 새 화면이면 필수")
    p_n.add_argument("--target", nargs="*", default=None,
                     help=("screen: 누를 대상. '라벨=text:문구' · '라벨=id:x' · '라벨=desc:x' "
                           "(뒤에 '|index=N') · 요소가 없을 때만 '라벨=at:0.5,0.8'. 픽셀은 거절. "
                           "--result 와 함께면 라벨만"))
    p_n.add_argument("--taps", nargs="*", help=argparse.SUPPRESS)   # 옛 픽셀 입력 — 거절하고 --target 을 안내
    p_n.add_argument("--screen-size", help="screen: 잰 화면 해상도. 예 1080x2400 (at 비율 변환 안내에 쓴다)")
    p_n.add_argument("--result", choices=["ok", "fail"], default=None,
                     help=("screen: 그 대상을 눌러 화면이 바뀌었으면 ok, 못 찾았거나 그대로면 fail / "
                           "pitfall·constraint: --index 항목을 다시 겪었으면 ok, 틀렸으면 fail"))
    p_n.add_argument("--index", type=int, default=None,
                     help="pitfall·constraint·forget: 항목 번호 (note show 의 index)")
    p_n.add_argument("--merge-into", dest="merge_into", type=int, default=None,
                     help="pitfall·constraint: 같은 지식으로 판단한 항목 번호 — 문장을 바꾸고 성적은 잇는다")
    p_n.add_argument("--kind", choices=["pitfall", "constraint"], default=None,
                     help="forget: 무엇을 지우나")
    p_n.add_argument("--all", action="store_true", help="show: 요약 대신 전부")
    p_n.add_argument("--apply", action="store_true", help="tidy: 계획대로 실제로 옮긴다 (없으면 계획만)")
    p_n.add_argument("--launch", nargs="*", default=None,
                     help="tidy: launch knowledge 로 옮길 함정과 영역을 직접 지정 ('번호=web' 등)")
    p_n.add_argument("--role", default=None,
                     help="screen: 어느 역할의 기기에서 쟀는지 (device --role 과 같은 키)")
    p_n.add_argument("--build", default=None,
                     help="screen: 그때 깔려 있던 빌드 표식 (device list 의 apk 값)")
    p_n.add_argument("--text",
                     help="constraint: 지켜야 할 것 / pitfall: 함정 / run: 결과 요약")
    p_n.add_argument("--check",
                     help="constraint: 밟으면서 무엇을 보면 위반을 알 수 있는지")
    p_n.add_argument("--targets",
                     help=f"target: 실제로 밟을 수 있는 것 ({'·'.join(TARGETS)}, 쉼표 구분)")
    p_n.add_argument("--why", help="target: 코드를 보고 그렇게 판단한 근거")
    p_n.add_argument(
        "--scope", choices=["project", "flutter", "platform"], default="project",
        help=("pitfall 범위. project=이 앱에서만 / flutter=모든 Flutter 앱 / "
              "platform=기기·OS 차원. project가 아니면 이 컴퓨터 범위(_machine)에 남긴다"))
    p_n.set_defaults(func=cmd_note)

    p_api = sub.add_parser("api", help="서버 시나리오를 밟는다 (target: server)")
    p_api.add_argument("--name", required=True, help="시나리오 이름")
    p_api.add_argument("--root", default=".", help="프로젝트 루트")
    p_api.add_argument("--base-url", dest="base_url", default=None,
                       help="API 주소. 생략하면 시나리오·설정에서 찾는다")
    p_api.add_argument("--timeout", type=int, default=30, help="요청당 제한 시간(초)")
    p_api.set_defaults(func=cmd_api)

    p_ot = sub.add_parser("other", help="앱·웹·서버가 아닌 것을 밟는다 (target: other)")
    p_ot.add_argument("action", choices=["run"])
    p_ot.add_argument("--root", default=".")
    p_ot.add_argument("--command", help="돌릴 명령. --name 과 둘 중 하나")
    p_ot.add_argument("--name", help="시나리오 이름. 끝까지 밟는다")
    p_ot.add_argument("--cwd", help="어디서 돌릴지 (기본: --root)")
    p_ot.add_argument("--watch", nargs="*", default=None,
                      help="실행 전후 파일 변화를 볼 경로. 주지 않으면 보지 않는다")
    p_ot.add_argument("--twice", action="store_true", help="두 번 돌려 같은지 본다")
    p_ot.add_argument("--env", nargs="*", default=None, help="K=V 형태로 여러 개")
    p_ot.add_argument("--timeout", type=int, default=120)
    p_ot.add_argument("--expect-exit", type=int, default=None)
    p_ot.add_argument("--expect-output", default=None)
    p_ot.add_argument("--expect-file", default=None)
    p_ot.add_argument("--expect-absent", default=None)
    p_ot.set_defaults(func=cmd_other)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # 옮긴 명령은 파서에 올리지 않고 그대로 넘긴다 — 인자 계약이 pro-launch 쪽에 산다
    if argv and argv[0] in MOVED:
        return delegate(argv)
    return run_cli(build_parser(), argv)


if __name__ == "__main__":
    sys.exit(main())
