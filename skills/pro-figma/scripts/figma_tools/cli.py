"""figma_cli 파서 조립 + 실행"""
from __future__ import annotations

from common.cli_parser import JSONArgumentParser, run_cli
from figma_tools.commands.assets import cmd_assets
from figma_tools.commands.conform import cmd_conform
from figma_tools.commands.coverage import cmd_coverage
from figma_tools.commands.diff import cmd_diff
from figma_tools.commands.output_path import cmd_output_path
from figma_tools.conform_probes import _ALL_CHECKS


def build_parser() -> JSONArgumentParser:
    # 인자 오류도 JSON(bad_args)으로 — 에이전트는 stdout JSON 만 읽는다 (#708)
    p = JSONArgumentParser(prog="figma_cli",
                           description="시안과 구현 화면을 대조한다")
    sub = p.add_subparsers(dest="command")

    c = sub.add_parser("coverage", help="덤프의 스타일 항목을 빠짐없이 나열한다")
    c.add_argument("--dump", required=True, help="Figma 덤프를 저장한 JSON 파일")
    c.add_argument("--node", default=None,
                   help="이 노드 아래만 본다 (생략하면 덤프 전체)")
    c.set_defaults(func=cmd_coverage)

    o = sub.add_parser("get-output-path", help="이번 대조의 산출물 자리를 만든다")
    o.add_argument("--title", required=True, help="이번 대조를 부를 이름 (화면 이름 등)")
    o.add_argument("--root", default=".", help="프로젝트 루트 (기본 현재 위치)")
    o.set_defaults(func=cmd_output_path)

    a_ = sub.add_parser("assets", help="내려받아야 할 에셋을 묶어 목록으로 낸다")
    a_.add_argument("--dump", required=True, help="Figma MCP 덤프 파일")
    a_.add_argument("--node", help="이 노드 아래만 (없으면 전체)")
    a_.set_defaults(func=cmd_assets)

    c_ = sub.add_parser("conform", help="시안 값대로 그려졌는지 속성으로 대조한다")
    c_.add_argument("--dump", required=True, help="Figma MCP 덤프 파일")
    c_.add_argument("--render", required=True, help="앱 렌더 png")
    c_.add_argument("--node", help="이 노드를 원점으로 (보통 화면 프레임)")
    c_.add_argument("--check", default="",
                    help=f"쉼표로 고른다 (기본 전부): {','.join(_ALL_CHECKS)}")
    c_.add_argument("--fail-on", dest="fail_on", default="none",
                    choices=["none", "low", "medium", "high"],
                    help="이 심각도 이상이면 종료코드 1 — CI 게이트용")
    c_.add_argument("--scale", type=float, default=0,
                    help="렌더 배율 (0이면 렌더 폭 ÷ 기준 노드 폭으로 추정)")
    c_.add_argument("--tolerance", type=int, default=12,
                    help="같은 색으로 볼 채널 차 (안티에일리어싱 여유)")
    c_.set_defaults(func=cmd_conform)

    d = sub.add_parser("diff", help="시안 export 와 앱 렌더를 픽셀로 맞댄다")
    d.add_argument("--render", required=True, help="앱이 그린 PNG")
    d.add_argument("--design", required=True, help="Figma export PNG")
    d.add_argument("--out", default=None, help="차이를 칠한 PNG 저장 경로")
    d.add_argument("--bg", default="auto",
                   help="합성 배경색 RRGGBB. 기본 auto = 시안 모서리에서 읽는다")
    d.add_argument("--threshold", type=int, default=24,
                   help="채널당 이 값을 넘어야 '다르다'로 본다 (기본 24)")
    d.add_argument("--mask-top", type=int, default=0,
                   help="위에서 이만큼 제외 (상태바 — 앱이 안 그린다)")
    d.add_argument("--mask-bottom", type=int, default=0,
                   help="아래에서 이만큼 제외 (홈 인디케이터)")
    d.add_argument("--min-area", type=int, default=200,
                   help="이 넓이 미만 덩어리는 보고하지 않는다")
    d.add_argument("--probe-shift", type=int, default=40,
                   help="렌더를 ±이 픽셀만큼 옮겨 보며 '통째로 밀림'인지 가린다 (0=끄기)")
    d.set_defaults(func=cmd_diff)
    return p


def main(argv: list[str] | None = None) -> int:
    return run_cli(build_parser(), argv)
