"""figma_cli 파서 조립 + 실행"""
from __future__ import annotations

from common.cli_parser import JSONArgumentParser, run_cli
from figma_tools.commands.assets import cmd_assets
from figma_tools.commands.conform import cmd_conform
from figma_tools.commands.coverage import cmd_coverage
from figma_tools.commands.diff import cmd_diff
from figma_tools.commands.fresh import cmd_check_fresh
from figma_tools.commands.ingest import cmd_ingest
from figma_tools.commands.token import cmd_token
from figma_tools.commands.output_path import cmd_output_path
from figma_tools.commands.store import STORE_IDS, cmd_store_check, cmd_store_specs
from figma_tools.conform_probes import _ALL_CHECKS


def build_parser() -> JSONArgumentParser:
    # 인자 오류도 JSON(bad_args)으로 — 에이전트는 stdout JSON 만 읽는다 (#708)
    p = JSONArgumentParser(prog="figma_cli",
                           description="Compare a Figma design with the implemented screen")
    sub = p.add_subparsers(dest="command")

    c = sub.add_parser("coverage", help="List every style entry in the dump")
    c.add_argument("--dump", required=True, help="JSON file holding the saved Figma dump")
    c.add_argument("--node", default=None,
                   help="Only look under this node (omit for the whole dump)")
    c.set_defaults(func=cmd_coverage)

    o = sub.add_parser("get-output-path", help="Create the output folder for this comparison")
    o.add_argument("--title", required=True, help="Name for this comparison (screen name, etc.)")
    o.add_argument("--root", default=".", help="Project root (default: current directory)")
    o.set_defaults(func=cmd_output_path)

    a_ = sub.add_parser("assets", help="Group the assets to download into a list")
    a_.add_argument("--dump", required=True, help="Figma MCP dump file")
    a_.add_argument("--node", help="Only under this node (omit for everything)")
    a_.set_defaults(func=cmd_assets)

    c_ = sub.add_parser("conform", help="Check property by property that the render matches the design values")
    c_.add_argument("--dump", required=True, help="Figma MCP dump file")
    c_.add_argument("--render", required=True, help="App render PNG")
    c_.add_argument("--node", help="Use this node as the origin (usually the screen frame)")
    c_.add_argument("--check", default="",
                    help=f"Comma-separated checks (default: all): {','.join(_ALL_CHECKS)}")
    c_.add_argument("--fail-on", dest="fail_on", default="none",
                    choices=["none", "low", "medium", "high"],
                    help="Exit code 1 at or above this severity (for CI gates)")
    c_.add_argument("--scale", type=float, default=0,
                    help="Render scale (0 = estimate as render width / origin node width)")
    c_.add_argument("--tolerance", type=int, default=12,
                    help="Per-channel difference still treated as the same color (anti-aliasing slack)")
    c_.set_defaults(func=cmd_conform)

    d = sub.add_parser("diff", help="Compare the design export and the app render pixel by pixel")
    d.add_argument("--render", required=True, help="PNG rendered by the app")
    d.add_argument("--design", required=True, help="Figma export PNG")
    d.add_argument("--out", default=None, help="Path to save a PNG with the differences painted")
    d.add_argument("--strict-size", dest="strict_size", action="store_true",
                   help="Stop with size_mismatch instead of silently resizing when render and design sizes differ")
    d.add_argument("--bg", default="auto",
                   help="Background color RRGGBB for compositing. Default auto = read from the design corner")
    d.add_argument("--threshold", type=int, default=24,
                   help="A pixel counts as different only when a channel differs by more than this (default 24)")
    d.add_argument("--mask-top", type=int, default=0,
                   help="Exclude this many pixels from the top (status bar, not drawn by the app)")
    d.add_argument("--mask-bottom", type=int, default=0,
                   help="Exclude this many pixels from the bottom (home indicator)")
    d.add_argument("--min-area", type=int, default=200,
                   help="Do not report clusters smaller than this area")
    d.add_argument("--probe-shift", type=int, default=40,
                   help="Shift the render by ± this many pixels to tell whether the whole area is offset (0 = off)")
    d.set_defaults(func=cmd_diff)

    # 시안 가져오기 · 변경 확인 (#1017)
    ig = sub.add_parser("ingest", help="Save a get_figma_data result file as a dump and record its lastModified")
    ig.add_argument("--source", required=True, help="File the harness saved the get_figma_data result to")
    ig.add_argument("--file-key", dest="file_key", required=True, help="Figma file key from the link")
    ig.add_argument("--node", default=None, help="Node id the dump was fetched for (238:1846)")
    ig.add_argument("--dump-dir", dest="dump_dir", required=True,
                    help="Folder to save into (the 'dump' path from get-output-path)")
    ig.set_defaults(func=cmd_ingest)

    cf = sub.add_parser("check-fresh", help="Check whether the design changed since the dump was ingested")
    cf.add_argument("--dump", required=True, help="Dump file saved by ingest")
    cf.set_defaults(func=cmd_check_fresh)

    tk = sub.add_parser("token", help="Show whether a Figma token is saved, or save one (value is never printed)")
    tk.add_argument("--prompt", action="store_true", help="Read the token typed in the terminal (hidden, needs a TTY)")
    tk.add_argument("--from-env", dest="from_env", default=None, help="Read the token from this environment variable")
    tk.add_argument("--name", default=None, help="Credential name to save as (default: the existing figma entry)")
    tk.set_defaults(func=cmd_token)

    # 스토어 이미지 하네스 (#884): 규격 정본 출력 / 폴더 판정
    ss = sub.add_parser("store-specs", help="Print the store image specs (sizes, counts, formats, sources)")
    ss.add_argument("--store", choices=STORE_IDS, default=None, help="Only this store (omit for all)")
    ss.set_defaults(func=cmd_store_specs)

    sc = sub.add_parser("store-check", help="Check a folder of store images against the specs")
    sc.add_argument("--dir", required=True, help="Folder laid out as {store}/{locale}/{slot}/*.png|jpg|jpeg")
    sc.add_argument("--locales", default=None,
                    help="Comma-separated target locales, first is the base (default: version.yml store_locales)")
    sc.add_argument("--root", default=".", help="Project root holding version.yml (default: current directory)")
    sc.set_defaults(func=cmd_store_check)
    return p


def main(argv: list[str] | None = None) -> int:
    return run_cli(build_parser(), argv)
