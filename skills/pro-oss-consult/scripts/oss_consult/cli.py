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
            raise argparse.ArgumentTypeError(f"{name} 는 정수여야 한다: {v}")
        if not lo <= n <= hi:
            raise argparse.ArgumentTypeError(f"{name} 는 {lo}~{hi} 범위여야 한다: {n}")
        return n
    return conv


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="oss_cli", description="oss-consult skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("collect", help="레포 하나의 오픈소스 준비 사실 수집")
    p.add_argument("target", help="OWNER/REPO")
    p.add_argument("--readme-lines", type=_int_range(1, MAX_TOP_LINES, "--readme-lines"), default=TOP_LINES,
                   help=f"README 앞부분 줄 수 (기본 {TOP_LINES}, 최대 {MAX_TOP_LINES})")
    p.set_defaults(func=collect.cmd_collect)

    p = sub.add_parser("local-facts", help="로컬 clone 의 변경 증폭·문구 하드코딩·의존성·추적 중인 비밀 파일 측정")
    p.add_argument("path", help="clone 한 저장소 경로 (하위 폴더도 됨)")
    p.add_argument("--commits", type=_int_range(1, 1000, "--commits"), default=200, help="분석할 최근 커밋 수 (1~1000)")
    p.set_defaults(func=local_facts.cmd_local_facts)

    p = sub.add_parser("list-repos", help="계정·조직의 레포 목록 (기본: 공개·비포크·비보관, 계정 소유만, 100개)")
    p.add_argument("owner", nargs="?", default=None, help="비우면 PAT 주인이 접근하는 전체")
    p.add_argument("--include-all", action="store_true", help="비공개·포크·보관 레포도 포함")
    p.add_argument("--include-other-owners", action="store_true", help="계정 인자가 있을 때 타 소유자(멤버 조직) 레포도 포함")
    p.add_argument("--limit", type=_int_range(0, 1000, "--limit"), default=_DEFAULT_LIMIT, help="최대 개수 (기본 100, 0 이면 전체)")
    p.set_defaults(func=list_repos.cmd_list_repos)

    p = sub.add_parser("get-output-path", help="컨설팅 보고서 저장 경로")
    p.add_argument("skill_id", nargs="?", default="oss-consult")
    p.add_argument("--title")
    p.add_argument("--cwd", help="보고서를 둘 레포 경로 (스크립트 폴더에서 실행할 때 작업 레포를 가리킨다)")
    p.set_defaults(func=get_output_path.cmd_get_output_path)

    p = sub.add_parser("repo-update", help="레포 About·topics·Discussions 변경 (승인 후, --dry-run 으로 계획 먼저)")
    p.add_argument("target", help="OWNER/REPO")
    p.add_argument("--description")
    p.add_argument("--homepage")
    p.add_argument("--topics", help="쉼표 구분. 기본은 기존 topics 에 더한다")
    p.add_argument("--topics-mode", choices=["add", "replace"], default="add")
    p.add_argument("--discussions", choices=["on", "off"])
    p.add_argument("--dry-run", action="store_true", help="쓰기 호출 없이 before(GET 으로 읽음)/planned 만 출력")
    p.set_defaults(func=repo_update.cmd_repo_update)

    p = sub.add_parser("label", help="라벨 생성·이름 변경·색 변경 (삭제 없음, 승인 후, --dry-run 으로 계획 먼저)")
    p.add_argument("target", help="OWNER/REPO")
    p.add_argument("action", choices=["create", "rename", "recolor"])
    p.add_argument("--name", help="대상 라벨 이름")
    p.add_argument("--new-name", help="rename 의 새 이름")
    p.add_argument("--color", help="6자리 16진수 (#는 있어도 없어도 됨)")
    p.add_argument("--description", help="라벨 설명 (100자 이하)")
    p.add_argument("--dry-run", action="store_true", help="쓰기 호출 없이 before(GET 으로 읽음)/planned 만 출력")
    p.set_defaults(func=label.cmd_label)

    return parser


def run_cli(parser: JSONArgumentParser, argv=None) -> int:
    """common.cli_parser.run_cli 와 같되 **모든 오류 JSON 에 next 를 채운다** (#660)."""
    try:
        args = parser.parse_args(argv)
    except _BadArgsExit as e:
        return emit({"ok": False, "code": "bad_args", "summary": e.message, "error": e.message,
                     "next": f"`{e.parser.prog} --help` 로 인자를 확인하고 고쳐 다시 실행한다"})
    if not hasattr(args, "func"):
        return emit({"ok": False, "code": "bad_args", "summary": "서브커맨드가 없다",
                     "next": "`oss_cli.py --help` 로 서브커맨드를 확인한다"})
    try:
        return args.func(args)
    except Exception as e:  # noqa: BLE001 — 어떤 실패도 JSON 으로 돌려준다
        return emit({"ok": False, "code": "handler_error", "summary": f"{type(e).__name__}: {e}",
                     "error": f"{type(e).__name__}: {e}",
                     "next": "입력을 확인하고 다시 실행한다. 계속되면 오류 내용을 사용자에게 보고한다"})


def main() -> int:
    return run_cli(build_parser())
