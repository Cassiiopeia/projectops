"""oss_cli 파서와 실행: 서브커맨드 선언 > 인자 해석 > 명령 실행 (모든 오류 JSON 에 next)
명령 함수는 모듈 속성으로 묶음 — 실행 시점의 함수를 부르게 해 테스트 대체가 반영됨
"""
from __future__ import annotations

from common.cli_parser import JSONArgumentParser, _BadArgsExit
from common.emit import emit

from oss_consult.commands import collect, get_output_path, label, list_repos, local_facts, repo_update
from oss_consult.commands.list_repos import _DEFAULT_LIMIT
from oss_consult.readme_facts import MAX_TOP_LINES, TOP_LINES

# ── 파서 ─────────────────────────────────────────────────────────────────

def _int_range(lo: int, hi: int, name: str):
    def conv(v: str) -> int:
        import argparse
        try:
            n = int(v)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{name} must be an integer: {v}")
        if not lo <= n <= hi:
            raise argparse.ArgumentTypeError(f"{name} must be in the range {lo}-{hi}: {n}")
        return n
    return conv


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="oss_cli", description="oss-consult skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("collect", help="Collect open-source readiness facts for one repo")
    p.add_argument("target", help="OWNER/REPO")
    p.add_argument("--readme-lines", type=_int_range(1, MAX_TOP_LINES, "--readme-lines"), default=TOP_LINES,
                   help=f"Number of README lines from the top (default {TOP_LINES}, max {MAX_TOP_LINES})")
    p.set_defaults(func=collect.cmd_collect)

    p = sub.add_parser("local-facts", help="Measure change amplification, hardcoded text, dependencies and tracked secret files in a local clone")
    p.add_argument("path", help="Path to the cloned repository (a subfolder also works)")
    p.add_argument("--commits", type=_int_range(1, 1000, "--commits"), default=200, help="Number of recent commits to analyze (1-1000)")
    p.set_defaults(func=local_facts.cmd_local_facts)

    p = sub.add_parser("list-repos", help="List an account's or organization's repos (default: public, non-fork, non-archived, owned by the account, 100)")
    p.add_argument("owner", nargs="?", default=None, help="Leave empty for everything the PAT owner can access")
    p.add_argument("--include-all", action="store_true", help="Also include private, forked and archived repos")
    p.add_argument("--include-other-owners", action="store_true", help="With an account argument, also include repos of other owners (member organizations)")
    p.add_argument("--limit", type=_int_range(0, 1000, "--limit"), default=_DEFAULT_LIMIT, help="Maximum count (default 100, 0 means all)")
    p.set_defaults(func=list_repos.cmd_list_repos)

    p = sub.add_parser("get-output-path", help="Save path for the consulting report")
    p.add_argument("skill_id", nargs="?", default="oss-consult")
    p.add_argument("--title")
    p.add_argument("--cwd", "--root", dest="cwd",
                   help="Path of the repo that holds the report (points at the working repo when run from the script folder)")
    p.set_defaults(func=get_output_path.cmd_get_output_path)

    p = sub.add_parser("repo-update", help="Change repo About, topics and Discussions (after approval; plan first with --dry-run)")
    p.add_argument("target", help="OWNER/REPO")
    p.add_argument("--description")
    p.add_argument("--homepage")
    p.add_argument("--topics", help="Comma-separated. Added to the existing topics by default")
    p.add_argument("--topics-mode", choices=["add", "replace"], default="add")
    p.add_argument("--discussions", choices=["on", "off"])
    p.add_argument("--dry-run", action="store_true", help="Print only before (read with GET) and planned, without write calls")
    p.set_defaults(func=repo_update.cmd_repo_update)

    p = sub.add_parser("label", help="Create, rename or recolor a label (no delete; after approval; plan first with --dry-run)")
    p.add_argument("target", help="OWNER/REPO")
    p.add_argument("action", choices=["create", "rename", "recolor"])
    p.add_argument("--name", help="Target label name")
    p.add_argument("--new-name", help="New name for rename")
    p.add_argument("--color", help="6-digit hex (leading # optional)")
    p.add_argument("--description", help="Label description (100 characters or fewer)")
    p.add_argument("--dry-run", action="store_true", help="Print only before (read with GET) and planned, without write calls")
    p.set_defaults(func=label.cmd_label)

    return parser


def run_cli(parser: JSONArgumentParser, argv=None) -> int:
    """common.cli_parser.run_cli 와 같되 **모든 오류 JSON 에 next 를 채운다** (#660)."""
    try:
        args = parser.parse_args(argv)
    except _BadArgsExit as e:
        return emit({"ok": False, "code": "bad_args", "summary": e.message, "error": e.message,
                     "next": f"Run `{e.parser.prog} --help` to check the arguments, fix them and run again"})
    if not hasattr(args, "func"):
        return emit({"ok": False, "code": "bad_args", "summary": "No subcommand given",
                     "next": "Run `oss_cli.py --help` to see the subcommands"})
    try:
        return args.func(args)
    except Exception as e:  # noqa: BLE001 — 어떤 실패도 JSON 으로 돌려준다
        return emit({"ok": False, "code": "handler_error", "summary": f"{type(e).__name__}: {e}",
                     "error": f"{type(e).__name__}: {e}",
                     "next": "Check the input and run again. If it keeps failing, report the error to the user"})


def main() -> int:
    return run_cli(build_parser())
