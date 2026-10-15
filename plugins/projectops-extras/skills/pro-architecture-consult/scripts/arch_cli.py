#!/usr/bin/env python3
"""arch_cli: pro-architecture-consult 사실 수집 CLI — 판단은 에이전트, 출력은 항상 JSON (ok·code·summary·next)

extras 플러그인은 자기 폴더만 설치되므로 scripts/common 을 쓰지 않는다 (표준 라이브러리 전용).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from arch import assets, deps, detect, diff_review, installer, ledger, rule_documents, scan  # noqa: E402

# 범주별 목록 최대 개수 기본값 (전체 수는 truncated 에 남는다)
DEFAULT_LIST_LIMIT = 50


class _BadArgumentsExit(Exception):
    def __init__(self, parser, message):
        super().__init__(message)
        self.parser, self.message = parser, message


class JsonArgumentParser(argparse.ArgumentParser):
    """인자 오류를 stderr 대신 JSON 으로 돌려주기 위한 파서"""

    def error(self, message):
        raise _BadArgumentsExit(self, message)


def emit(payload: dict) -> int:
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0 if payload["ok"] else 1


def _project_root(raw: str) -> Path | None:
    path = Path(raw).expanduser().resolve()
    return path if path.is_dir() else None


# 서브커맨드: 경로 확인 > 모듈 호출 > next 힌트

def cmd_detect(args, root):
    return {**detect.detect_project(root), "next": f"scan {root}"}


def cmd_scan(args, root):
    result = scan.scan_project(root, args.limit, args.all, args.only, args.category)
    if args.record:
        rule_counts = {r["id"]: r.get("violations", 0) for r in ledger.check_rules(root)["rules"]}
        result["recorded"] = str(scan.record_metrics(root, result["counts"], rule_counts))
    summary_text = result.pop("summary_text")
    return {**result, "summary": summary_text,
            "next": f"review_order 순서로 원문 확인 (references/facts.md) · assets {root} · deps {root} · rule-docs {root}"}


def cmd_assets(args, root):
    return {**assets.scan_assets(root, args.limit), "next": f"deps {root}"}


def cmd_deps(args, root):
    return {**deps.analyze_dependencies(root, args.limit, args.all),
            "next": f"layer_edges 로 전체 그림 확인 후 위반 원문 확인 (references/facts.md) · rule-docs {root}"}


def cmd_diff(args, root):
    result = diff_review.review_diff(root, args.base, args.limit)
    if result.get("ok") is False:
        return result
    if ledger.load_rules(root):
        check = ledger.check_rules(root)
        result["ledger_new_violations"] = [{"rule": r["id"], **n} for r in check["rules"] for n in r.get("new", [])]
    return {**result, "next": "고칠 목록을 사용자에게 보여 주고 승인 뒤 수정 (references/check.md)"}


def cmd_rule_docs(args, root):
    return {**rule_documents.inspect_rule_documents(root), "next": "모순은 원문을 읽고 판단한다 (references/audit.md)"}


def cmd_ledger(args, root):
    if args.action == "check":
        result = ledger.check_rules(root)
        verdict = "fail" if result["failing_rules"] else "pass"
        return {**result, "verdict": verdict, "summary": f"규칙 {len(result['rules'])}개, 실패 {result['failing_rules']}",
                "next": f"ledger {root} tighten (고쳐진 항목 정리)" if verdict == "fail" else None}
    if args.action == "freeze":
        if not args.rule:
            return {"ok": False, "code": "bad_args", "summary": "freeze 는 --rule ID 가 필요하다",
                    "next": f"ledger {root} freeze --rule <id>"}
        return ledger.freeze_rule(root, args.rule)
    return {**ledger.tighten_rules(root), "next": f"ledger {root} check"}


def cmd_conventions(args, root):
    stacks = args.stack or []
    if args.action == "check":
        return {**installer.check_installed(root, stacks), "next": None}
    return installer.install_documents(root, stacks, args.force)


def cmd_install_tests(args, root):
    return installer.install_rule_test(root, args.stack, args.module, args.force)


def cmd_get_output_path(args, root):
    return {**installer.audit_output_path(root, args.title), "next": "보고서 형식: references/report-template.md"}


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="arch_cli", description="pro-architecture-consult 사실 수집 CLI")
    sub = parser.add_subparsers(dest="command", parser_class=JsonArgumentParser)

    def add(name, handler, help_text, has_limit=False):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("path", help="대상 프로젝트 루트")
        if has_limit:
            command.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT, help="범주별 목록 최대 개수")
        command.set_defaults(handler=handler)
        return command

    add("detect", cmd_detect, "스택·규칙 문서·이어받을 자료")
    scan_command = add("scan", cmd_scan, "레포가 소유한 코드의 냄새 사실", has_limit=True)
    scan_command.add_argument("--record", action="store_true", help="docs/architecture/metrics.jsonl 에 요약 1줄 추가")
    scan_command.add_argument("--all", action="store_true", help="도구 설치물·생성물·외부 라이브러리도 포함 (origin 태그)")
    scan_command.add_argument("--only", action="append", metavar="PREFIX", help="이 경로 아래만 (여러 번) — 하위 에이전트용")
    scan_command.add_argument("--category", action="append", choices=scan.PER_FILE_CATEGORIES + scan.CROSS_FILE_CATEGORIES,
                              help="이 범주만 출력 (여러 번)")
    add("assets", cmd_assets, "이미지·폰트 사본과 같은 이름·다른 내용", has_limit=True)
    add("deps", cmd_deps, "계층 역방향 import · 모듈 간 저장소 직접 사용 · Gradle 모듈 순환", has_limit=True).add_argument(
        "--all", action="store_true", help="도구 설치물·생성물·외부 라이브러리도 포함")
    add("diff", cmd_diff, "변경분만 검사", has_limit=True).add_argument(
        "--base", default="HEAD", help="비교 기준 커밋 (기본 HEAD — 아직 커밋 안 한 변경)")
    add("rule-docs", cmd_rule_docs, "규칙 문서의 없는 경로·줄글 주석 유도 문구")
    ledger_command = add("ledger", cmd_ledger, "동결 목록 판정·최초 동결·정리")
    ledger_command.add_argument("action", choices=["check", "freeze", "tighten"])
    ledger_command.add_argument("--rule", help="freeze 대상 규칙 id")
    conventions_command = add("conventions", cmd_conventions, "규칙 정본 설치·상태 확인")
    conventions_command.add_argument("action", choices=["install", "check"])
    conventions_command.add_argument("--stack", action="append", choices=installer.STACKS, help="스택 문서도 (여러 번)")
    conventions_command.add_argument("--force", action="store_true", help="기존 설치본 덮어쓰기 (사용자 요청 시만)")
    tests_command = add("install-tests", cmd_install_tests, "규칙 테스트 템플릿 설치")
    tests_command.add_argument("--stack", required=True, choices=installer.STACKS)
    tests_command.add_argument("--module", default=".", help="레포 루트 기준 모듈 폴더 (예: app)")
    tests_command.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기 (사용자 요청 시만)")
    add("get-output-path", cmd_get_output_path, "감사 보고서 경로").add_argument("--title", required=True)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except _BadArgumentsExit as error:
        return emit({"ok": False, "code": "bad_args", "summary": error.message, "error": error.message,
                     "next": f"`{error.parser.prog} --help` 로 인자를 확인한다"})
    if not getattr(args, "handler", None):
        return emit({"ok": False, "code": "bad_args", "summary": "서브커맨드가 없다", "next": "`arch_cli.py --help`"})
    root = _project_root(args.path)
    if root is None:
        return emit({"ok": False, "code": "path_not_found", "summary": f"폴더가 아니다: {args.path}",
                     "next": "대상 프로젝트 루트 경로를 넘긴다"})
    try:
        return emit(args.handler(args, root))
    except Exception as error:  # noqa: BLE001 — 어떤 실패도 JSON 으로
        return emit({"ok": False, "code": "handler_error", "summary": f"{type(error).__name__}: {error}",
                     "next": "입력을 확인하고 다시 실행한다. 계속되면 오류를 사용자에게 보고한다"})


if __name__ == "__main__":
    sys.exit(main())
