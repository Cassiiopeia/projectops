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
        description="agent QA — walk the app, web or server to find bugs (running and capturing is pro-launch)",
        epilog=("Moved commands: " + " · ".join(MOVED)
                + " — forwarded to pro-launch's launch_cli.py (removed in the next minor)"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_d = sub.add_parser("detect", help="what can be walked (pro-launch detect + note target)")
    p_d.add_argument("--path", default=".", help="search start path (default: current directory)")
    p_d.add_argument("--target", default=None,
                     help=f"set the target to walk directly ({'·'.join(TARGETS)}). Detected when omitted")
    p_d.set_defaults(func=cmd_detect)

    p_sc = sub.add_parser("scenario", help="manage per-project walk scenarios")
    p_sc.add_argument("action", choices=["init", "list", "show"])
    p_sc.add_argument("--target", default=DEFAULT_TARGET,
                      help=f"what drives it ({'·'.join(TARGETS)}, default {DEFAULT_TARGET})")
    p_sc.add_argument("--name", help="scenario file name (without extension)")
    p_sc.add_argument("--root", default=".", help="project root")
    p_sc.add_argument("--group",
                      help="init: create under flows/{group}/. _shared makes it a precondition")
    p_sc.add_argument("--force", action="store_true", help="overwrite on init")
    p_sc.set_defaults(func=cmd_scenario)

    p_n = sub.add_parser("note", help="record what was learned about this project")
    p_n.add_argument("action",
                     choices=["show", "target", "constraint", "screen", "pitfall", "run",
                              "tidy", "forget"])
    p_n.add_argument("--root", default=".")
    p_n.add_argument("--name", help="screen: screen name / run: scenario name")
    p_n.add_argument("--anchor", help="screen: clue that identifies this screen (text etc.). Required for a new screen")
    p_n.add_argument("--target", nargs="*", default=None,
                     help=("screen: what to press. 'label=text:copy' · 'label=id:x' · 'label=desc:x' "
                           "(append '|index=N') · 'label=at:0.5,0.8' only when there is no element. Pixels are rejected. "
                           "With --result, labels only"))
    p_n.add_argument("--taps", nargs="*", help=argparse.SUPPRESS)   # 옛 픽셀 입력 — 거절하고 --target 을 안내
    p_n.add_argument("--screen-size", help="screen: measured screen resolution, e.g. 1080x2400 (used for at-ratio hints)")
    p_n.add_argument("--result", choices=["ok", "fail"], default=None,
                     help=("screen: ok if pressing that target changed the screen, fail if not found or unchanged / "
                           "pitfall·constraint: ok if the --index entry happened again, fail if it was wrong"))
    p_n.add_argument("--index", type=int, default=None,
                     help="pitfall·constraint·forget: entry number (index in note show)")
    p_n.add_argument("--merge-into", dest="merge_into", type=int, default=None,
                     help="pitfall·constraint: number of the entry judged to be the same knowledge — replaces the text, keeps the record")
    p_n.add_argument("--kind", choices=["pitfall", "constraint"], default=None,
                     help="forget: what to delete")
    p_n.add_argument("--all", action="store_true", help="show: everything instead of a summary")
    p_n.add_argument("--apply", action="store_true", help="tidy: actually move per the plan (plan only without it)")
    p_n.add_argument("--launch", nargs="*", default=None,
                     help="tidy: pick pitfalls to move to launch knowledge and their area ('number=web' etc.)")
    p_n.add_argument("--role", default=None,
                     help="screen: role of the device it was measured on (same key as device --role)")
    p_n.add_argument("--build", default=None,
                     help="screen: build marker installed at the time (apk value in device list)")
    p_n.add_argument("--text",
                     help="constraint: what must hold / pitfall: the pitfall / run: result summary")
    p_n.add_argument("--check",
                     help="constraint: what to watch while walking to spot a violation")
    p_n.add_argument("--targets",
                     help=f"target: what can actually be walked ({'·'.join(TARGETS)}, comma-separated)")
    p_n.add_argument("--why", help="target: evidence from the code for that judgment")
    p_n.add_argument(
        "--scope", choices=["project", "flutter", "platform"], default="project",
        help=("pitfall scope. project=this app only / flutter=every Flutter app / "
              "platform=device or OS level. Anything but project is kept at this machine's scope (_machine)"))
    p_n.set_defaults(func=cmd_note)

    p_api = sub.add_parser("api", help="walk a server scenario (target: server)")
    p_api.add_argument("--name", required=True, help="scenario name")
    p_api.add_argument("--root", default=".", help="project root")
    p_api.add_argument("--base-url", dest="base_url", default=None,
                       help="API address. Looked up in the scenario and config when omitted")
    p_api.add_argument("--timeout", type=int, default=30, help="time limit per request (seconds)")
    p_api.set_defaults(func=cmd_api)

    p_ot = sub.add_parser("other", help="walk something that is not an app, web or server (target: other)")
    p_ot.add_argument("action", choices=["run"])
    p_ot.add_argument("--root", default=".")
    p_ot.add_argument("--command", help="command to run. One of this or --name")
    p_ot.add_argument("--name", help="scenario name. Walked to the end")
    p_ot.add_argument("--cwd", help="where to run (default: --root)")
    p_ot.add_argument("--watch", nargs="*", default=None,
                      help="paths to watch for file changes before and after the run. Not watched when omitted")
    p_ot.add_argument("--twice", action="store_true", help="run twice and check the results match")
    p_ot.add_argument("--env", nargs="*", default=None, help="several, as K=V")
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
