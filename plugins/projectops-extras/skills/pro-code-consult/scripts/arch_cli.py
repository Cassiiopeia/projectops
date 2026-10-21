#!/usr/bin/env python3
"""arch_cli: pro-code-consult 사실 수집 CLI — 판단은 에이전트, 출력은 항상 JSON (ok·code·summary·next)

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
            "next": f"Open the source in review_order order (references/facts.md) · assets {root} · deps {root} · rule-docs {root}"}


def cmd_assets(args, root):
    return {**assets.scan_assets(root, args.limit), "next": f"deps {root}"}


def cmd_deps(args, root):
    return {**deps.analyze_dependencies(root, args.limit, args.all),
            "next": f"Check the overall picture with layer_edges, then open the violating source (references/facts.md) · rule-docs {root}"}


def cmd_diff(args, root):
    result = diff_review.review_diff(root, args.base, args.limit)
    if result.get("ok") is False:
        return result
    if ledger.load_rules(root):
        check = ledger.check_rules(root)
        result["ledger_new_violations"] = [{"rule": r["id"], **n} for r in check["rules"] for n in r.get("new", [])]
    return {**result, "next": "Show the fix list to the user and fix after approval (references/check.md)"}


def cmd_rule_docs(args, root):
    return {**rule_documents.inspect_rule_documents(root), "next": "Judge contradictions by reading the source documents (references/audit.md)"}


def cmd_ledger(args, root):
    if args.action == "check":
        result = ledger.check_rules(root)
        verdict = "fail" if result["failing_rules"] else "pass"
        return {**result, "verdict": verdict, "summary": f"{len(result['rules'])} rules, {result['failing_rules']} failing",
                "next": f"ledger {root} tighten (clean up fixed entries)" if verdict == "fail" else None}
    if args.action == "freeze":
        if not args.rule:
            return {"ok": False, "code": "bad_args", "summary": "freeze needs --rule ID",
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
    return {**installer.audit_output_path(root, args.title), "next": "Report format: references/report-template.md"}


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="arch_cli", description="pro-code-consult fact-gathering CLI")
    sub = parser.add_subparsers(dest="command", parser_class=JsonArgumentParser)

    def add(name, handler, help_text, has_limit=False):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("path", help="Target project root")
        if has_limit:
            command.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT, help="Maximum list size per category")
        command.set_defaults(handler=handler)
        return command

    add("detect", cmd_detect, "Stacks, rule documents and prior material to pick up")
    scan_command = add("scan", cmd_scan, "Smell facts for code the repo owns", has_limit=True)
    scan_command.add_argument("--record", action="store_true", help="Append a one-line summary to docs/architecture/metrics.jsonl")
    scan_command.add_argument("--all", action="store_true", help="Also include tool installs, generated files and third-party libraries (origin tag)")
    scan_command.add_argument("--only", action="append", metavar="PREFIX", help="Only under this path (repeatable), for sub-agents")
    scan_command.add_argument("--category", action="append", choices=scan.PER_FILE_CATEGORIES + scan.CROSS_FILE_CATEGORIES,
                              help="Output only this category (repeatable)")
    add("assets", cmd_assets, "Image and font copies, and same name with different content", has_limit=True)
    add("deps", cmd_deps, "Reverse layer imports, direct cross-module repository use, Gradle module cycles", has_limit=True).add_argument(
        "--all", action="store_true", help="Also include tool installs, generated files and third-party libraries")
    add("diff", cmd_diff, "Check only the diff", has_limit=True).add_argument(
        "--base", default="HEAD", help="Base commit to compare against (default HEAD: uncommitted changes)")
    add("rule-docs", cmd_rule_docs, "Missing paths and prose-comment inducing text in rule documents")
    ledger_command = add("ledger", cmd_ledger, "Freeze list check, first freeze and cleanup")
    ledger_command.add_argument("action", choices=["check", "freeze", "tighten"])
    ledger_command.add_argument("--rule", help="Rule id to freeze")
    conventions_command = add("conventions", cmd_conventions, "Install the canonical conventions or check their status")
    conventions_command.add_argument("action", choices=["install", "check"])
    conventions_command.add_argument("--stack", action="append", choices=installer.STACKS, help="Also the stack document (repeatable)")
    conventions_command.add_argument("--force", action="store_true", help="Overwrite the existing install (only when the user asks)")
    tests_command = add("install-tests", cmd_install_tests, "Install the rule test template")
    tests_command.add_argument("--stack", required=True, choices=installer.STACKS)
    tests_command.add_argument("--module", default=".", help="Module folder relative to the repo root (e.g. app)")
    tests_command.add_argument("--force", action="store_true", help="Overwrite the existing file (only when the user asks)")
    add("get-output-path", cmd_get_output_path, "Audit report path").add_argument("--title", required=True)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except _BadArgumentsExit as error:
        return emit({"ok": False, "code": "bad_args", "summary": error.message, "error": error.message,
                     "next": f"Check the arguments with `{error.parser.prog} --help`"})
    if not getattr(args, "handler", None):
        return emit({"ok": False, "code": "bad_args", "summary": "No subcommand given", "next": "`arch_cli.py --help`"})
    root = _project_root(args.path)
    if root is None:
        return emit({"ok": False, "code": "path_not_found", "summary": f"Not a directory: {args.path}",
                     "next": "Pass the target project root path"})
    try:
        return emit(args.handler(args, root))
    except Exception as error:  # noqa: BLE001 — 어떤 실패도 JSON 으로
        return emit({"ok": False, "code": "handler_error", "summary": f"{type(error).__name__}: {error}",
                     "next": "Check the input and run again. If it keeps failing, report the error to the user"})


if __name__ == "__main__":
    sys.exit(main())
