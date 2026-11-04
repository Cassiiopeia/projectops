"""figma_cli 파서 조립 + 실행"""
from __future__ import annotations

from common.cli_parser import JSONArgumentParser, run_cli
from figma_tools.commands.assets import cmd_assets
from figma_tools.commands.conform import cmd_conform
from figma_tools.commands.compose import cmd_store_compose
from figma_tools.commands.coverage import cmd_coverage
from figma_tools.commands.diff import cmd_diff
from figma_tools.commands.fetch import cmd_fetch
from figma_tools.commands.fresh import cmd_check_fresh
from figma_tools.commands.screens import DEFAULT_DEPTH, cmd_screens
from figma_tools.commands.svg_check import cmd_svg_check
from figma_tools.commands.ingest import cmd_ingest
from figma_tools.commands.token import cmd_token
from figma_tools.commands.output_path import cmd_output_path
from figma_tools.commands.store import STORE_IDS, cmd_store_check, cmd_store_specs
from figma_tools.commands.store_pages import cmd_store_pages
from figma_tools.commands.store_upload import (
    UPLOAD_STATUSES, cmd_store_upload_mark, cmd_store_upload_plan, cmd_store_upload_status,
)
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
    c_.add_argument("--mask-top", dest="mask_top", type=int, default=0,
                    help="Skip shapes inside this many logical px from the top (status bar, drawn by the OS)")
    c_.add_argument("--mask-bottom", dest="mask_bottom", type=int, default=0,
                    help="Skip shapes inside this many logical px from the bottom (home indicator)")
    c_.add_argument("--mask-node", dest="mask_node", action="append", default=None,
                    help="Skip this node (repeatable), e.g. a photo placeholder that data fills")
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
    d.add_argument("--mask-data", dest="mask_data", default=None,
                   help="Leave out data that mock data changes: text, image or text,image (needs --dump, --node)")
    d.add_argument("--mask-node", dest="mask_node", action="append", default=None,
                   help="Also leave out this node's box (repeatable), e.g. a designer's gray photo placeholder")
    d.add_argument("--dump", default=None, help="Dump of the screen, for --mask-data / --mask-node")
    d.add_argument("--node", default=None, help="Screen node id in the dump, for --mask-data")
    d.add_argument("--solids", action="store_true",
                   help="Also list clusters where a flat color area exists on one side only (not text)")
    d.add_argument("--rows", action="store_true",
                   help="Also pair text rows by height and report shifts and unpaired rows (moving backgrounds)")
    d.add_argument("--scale", type=float, default=1.0, help="Pixels per logical px, for --rows (default 1)")
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

    sv = sub.add_parser("svg-check", help="Find SVG features renderers often drop (filter, style, text, gradientTransform)")
    sv.add_argument("--dir", required=True, help="Folder holding the downloaded SVG assets")
    sv.set_defaults(func=cmd_svg_check)

    sc = sub.add_parser("screens", help="List the screens under a node (or the whole file) with the saved token")
    sc.add_argument("--file-key", dest="file_key", required=True, help="Figma file key from the link")
    sc.add_argument("--node", default=None, help="Node id from the link (238-1846 is 238:1846); omit for the whole file")
    sc.add_argument("--depth", type=int, default=DEFAULT_DEPTH,
                    help=f"How many levels of pages and sections to look into (default {DEFAULT_DEPTH})")
    sc.set_defaults(func=cmd_screens)

    fe = sub.add_parser("fetch", help="Fetch one node from Figma with the saved token and save it as a dump (no MCP)")
    fe.add_argument("--file-key", dest="file_key", required=True, help="Figma file key from the link")
    fe.add_argument("--node", required=True, help="Node id to fetch (link node-id 238-1846 is 238:1846)")
    fe.add_argument("--dump-dir", dest="dump_dir", required=True,
                    help="Folder to save into (the 'dump' path from get-output-path)")
    fe.add_argument("--design-dir", dest="design_dir", default=None,
                    help="Also export the node as PNG into this folder (the 'design' path)")
    fe.add_argument("--scale", type=float, default=1, help="PNG export scale, match the device (default 1)")
    fe.add_argument("--version", default=None,
                    help="Fetch a past design from the file's version history (version id) instead of the current one")
    fe.set_defaults(func=cmd_fetch)

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

    # 스토어 이미지 합성 (#1021): 장면 파일 > 언어별 HTML + 렌더 스크립트
    sp = sub.add_parser("store-compose", help="Build per-locale store image HTML and a render script from scenes.json")
    sp.add_argument("--run-dir", dest="run_dir", required=True,
                    help="run_dir printed by get-output-path (everything is written under <run_dir>/store)")
    sp.add_argument("--scenes", default=None, help="Scenes file (default: <run_dir>/store/scenes.json)")
    sp.add_argument("--locales", default=None,
                    help="Comma-separated target locales, first is the base (default: version.yml store_locales, then the locales in scenes)")
    sp.add_argument("--store", choices=STORE_IDS, default=None, help="Only this store (omit for all outputs)")
    sp.add_argument("--root", default=".", help="Project root holding version.yml (default: current directory)")
    sp.set_defaults(func=cmd_store_compose)

    # 언어별 랜딩 페이지 (#1021): pages.json > site/ (hreflang · sitemap)
    pg = sub.add_parser("store-pages", help="Build per-locale landing pages with hreflang links and a sitemap")
    pg.add_argument("--run-dir", dest="run_dir", required=True,
                    help="run_dir printed by get-output-path (pages go to <run_dir>/store/site)")
    pg.add_argument("--pages", default=None, help="Pages file (default: <run_dir>/store/pages.json)")
    pg.add_argument("--root", default=".", help="Project root (default: current directory)")
    pg.set_defaults(func=cmd_store_pages)

    # 콘솔 업로드 체크리스트 (#1021): 업로드는 pro-launch web, 진행 기록만 여기서
    up = sub.add_parser("store-upload-plan", help="Make the console upload checklist from a store-check ready folder")
    up.add_argument("--dir", required=True, help="Store image folder that passes store-check")
    up.add_argument("--locales", default=None, help="Comma-separated target locales (same as store-check)")
    up.add_argument("--out", default=None, help="Checklist path (default: <dir>/../upload_checklist.json)")
    up.add_argument("--root", default=".", help="Project root holding version.yml (default: current directory)")
    up.set_defaults(func=cmd_store_upload_plan)

    um = sub.add_parser("store-upload-mark", help="Record one checklist item's upload step")
    um.add_argument("--checklist", required=True, help="upload_checklist.json from store-upload-plan")
    um.add_argument("--key", required=True, help="Item key store/locale/slot (ios/en-US/iphone-dynamic-island-large)")
    um.add_argument("--status", required=True, choices=UPLOAD_STATUSES, help="Step reached")
    um.add_argument("--note", default=None, help="Short note (what the console showed)")
    um.set_defaults(func=cmd_store_upload_mark)

    us = sub.add_parser("store-upload-status", help="Show upload progress and the final per-locale, per-slot report")
    us.add_argument("--checklist", required=True, help="upload_checklist.json from store-upload-plan")
    us.set_defaults(func=cmd_store_upload_status)
    return p


def main(argv: list[str] | None = None) -> int:
    return run_cli(build_parser(), argv)
