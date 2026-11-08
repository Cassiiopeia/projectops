#!/usr/bin/env python3
"""disk_cli: pro-disk-cleanup 사실 수집·삭제 게이트 CLI — 판단은 에이전트, 출력은 항상 JSON (ok·code·summary·next)

extras 플러그인은 자기 폴더만 설치되므로 scripts/common 을 쓰지 않는다 (표준 라이브러리 전용).
삭제 명령은 --yes 없으면 계획만 돌려준다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from disk import (catalog, cleaners, docker_cleanup, generated, guard, removal, scan_report,  # noqa: E402
                  settings, sizes, worktrees)
from disk.processes import ProcessSnapshot  # noqa: E402


class _BadArgumentsExit(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class JsonArgumentParser(argparse.ArgumentParser):
    """인자 오류를 stderr 대신 JSON 으로 돌려주기 위한 파서"""

    def error(self, message):
        raise _BadArgumentsExit(message)


def emit(payload: dict) -> int:
    payload.setdefault("ok", True)
    payload.setdefault("code", "ok" if payload["ok"] else "error")
    payload.setdefault("summary", None)
    payload.setdefault("next", None)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()
    return 0 if payload["ok"] else 1


# 서브커맨드: 입력 해석 > 모듈 호출 > 결과 + next

def cmd_free(_args) -> dict:
    space = sizes.free_space()
    return {"free_space": space, "summary": f"{space['free_gb']} GB free ({space['used_percent']}% used)"}


def cmd_scan(args) -> dict:
    roots, source = settings.worktree_roots(args.roots)
    report = scan_report.build(roots, settings.idle_hours(args.idle_hours), args.skip_worktrees, args.max_seconds)
    return {**report, "roots_source": source}


def cmd_worktrees(args) -> dict:
    roots, source = settings.worktree_roots(args.roots)
    facts = [item for item in worktrees.collect(roots, settings.idle_hours(args.idle_hours), args.with_size)
             if args.include_main or not item["is_main"]]
    numbers = sorted({(item["repository"], item["issue_number"]) for item in facts if item.get("issue_number")},
                     key=lambda pair: (pair[0] or "", pair[1]))
    return {"roots": [str(root) for root in roots], "roots_source": source, "worktrees": facts,
            "issues_to_check": [{"repository": repository, "issue_number": number} for repository, number in numbers],
            "summary": f"{len(facts)} worktrees, {len(numbers)} linked issues to check",
            "next": "pro-github get-issue for each issues_to_check entry, then remove-worktree PATH --closed-issue N"}


def _generated_candidates(args) -> tuple[list[dict], list[dict]]:
    roots, _ = settings.worktree_roots(args.roots)
    idle = settings.idle_hours(args.idle_hours)
    snapshot = ProcessSnapshot()
    candidates, skipped_worktrees = [], []
    for item in worktrees.collect(roots, idle, with_size=False, snapshot=snapshot):
        if (item["is_main"] and not args.include_main) or item.get("is_missing"):
            continue
        if item.get("is_in_use"):
            skipped_worktrees.append({"path": item["path"], "skip_reason": "in_use", "in_use_by": item["in_use_by"]})
            continue
        worktree = Path(item["path"])
        for folder in generated.find_generated_folders(worktree):
            candidates.append({**generated.describe_folder(worktree, folder, idle, snapshot.users_of(folder)),
                               "worktree": item["path"]})
    return sorted(candidates, key=lambda row: -row["size_bytes"]), skipped_worktrees


def cmd_generated(args) -> dict:
    candidates, skipped_worktrees = _generated_candidates(args)
    reclaimable = [row for row in candidates if not row["skip_reason"]]
    total = sizes.to_gigabytes(sum(row["size_bytes"] for row in reclaimable))
    return {"candidates": candidates, "skipped_worktrees": skipped_worktrees, "reclaimable_gb": total,
            "summary": f"{len(reclaimable)} of {len(candidates)} build-output folders can go ({total} GB)",
            "next": "clear-generated --yes"}


def cmd_clear_generated(args) -> dict:
    candidates, skipped_worktrees = _generated_candidates(args)
    results = {"skipped_worktrees": skipped_worktrees, "removed": [], "refused": []}
    chosen = [row for row in candidates if not row["skip_reason"]]
    if not args.yes:
        total = sizes.to_gigabytes(sum(row["size_bytes"] for row in chosen))
        return {**results, "code": "dry_run", "planned": chosen, "planned_gb": total,
                "skipped": [row for row in candidates if row["skip_reason"]],
                "summary": f"{len(chosen)} folders ({total} GB) would be removed. Re-run with --yes"}
    free_before = sizes.free_bytes()
    for row in chosen:
        outcome = guard.remove_tree(row["path"], Path(row["worktree"]))
        results["removed" if outcome["removed"] else "refused"].append(outcome)
    freed = sizes.to_gigabytes(max(sizes.free_bytes() - free_before, 0))
    return {**results, "ok": not results["refused"], "code": "cleaned", "freed_gb": freed,
            "kept": [row for row in candidates if row["skip_reason"]],
            "summary": f"Removed {len(results['removed'])} folders, freed {freed} GB; "
                       f"{len(candidates) - len(chosen)} kept (tracked, recent or in use)"}


def cmd_remove_worktree(args) -> dict:
    return removal.remove(args.path, args.closed_issue, args.approved_stale, settings.idle_hours(args.idle_hours),
                          settings.backup_root(args.backup_dir), args.yes, args.skip_large_untracked)


def _location_or_failure(key: str, kinds: tuple[str, ...]) -> tuple[catalog.Location | None, dict | None]:
    location = catalog.find(key)
    if location and location.kind in kinds:
        return location, None
    valid = [item.key for item in catalog.locations() if item.kind in kinds]
    return None, {"ok": False, "code": "unknown_location", "valid_keys": valid,
                  "summary": f"`{key}` is not a {'/'.join(kinds)} location on this OS"}


def cmd_aged(args) -> dict:
    location, failure = _location_or_failure(args.key, ("aged",))
    if failure:
        return failure
    snapshot = ProcessSnapshot()
    candidates = cleaners.aged_candidates(location, args.older_than_days, snapshot)
    result = cleaners.delete_candidates(candidates, location.path, args.yes)
    return {**result, "location": location.key, "tier": location.tier, "older_than_days": args.older_than_days,
            "running_builds": snapshot.is_running("xcodebuild", "XCBBuildService", "GradleDaemon")}


def cmd_tool(args) -> dict:
    location, failure = _location_or_failure(args.key, ("tool",))
    if failure:
        return failure
    return {**cleaners.run_tool(location, args.yes), "location": location.key, "tier": location.tier}


def cmd_browser(args) -> dict:
    location, _ = _location_or_failure("projectops-browser", ("browser",))
    candidates = cleaners.browser_candidates(location, ProcessSnapshot())
    return {**cleaners.delete_candidates(candidates, location.path, args.yes), "location": location.key}


def cmd_docker(args) -> dict:
    if not (args.volumes or args.images or args.containers):
        return docker_cleanup.facts()
    return docker_cleanup.clean(args.volumes, args.images, args.containers or [], args.yes)


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="disk_cli.py", description="Find and clear reclaimable disk space safely")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)

    def with_roots(sub):
        sub.add_argument("--roots", nargs="+", help="folders to search for repositories and worktrees")
        sub.add_argument("--idle-hours", type=float, help="keep anything touched within this many hours (default 2)")
        return sub

    commands.add_parser("free").set_defaults(handler=cmd_free)
    scan = with_roots(commands.add_parser("scan"))
    scan.add_argument("--skip-worktrees", action="store_true")
    scan.add_argument("--max-seconds", type=int, default=sizes.FOLDER_MEASURE_SECONDS)
    scan.set_defaults(handler=cmd_scan)
    listing = with_roots(commands.add_parser("worktrees"))
    listing.add_argument("--with-size", action="store_true")
    listing.add_argument("--include-main", action="store_true")
    listing.set_defaults(handler=cmd_worktrees)
    for name, handler in (("generated", cmd_generated), ("clear-generated", cmd_clear_generated)):
        sub = with_roots(commands.add_parser(name))
        sub.add_argument("--include-main", action="store_true", help="also main checkouts, not only worktrees")
        if name == "clear-generated":
            sub.add_argument("--yes", action="store_true")
        sub.set_defaults(handler=handler)
    remove = commands.add_parser("remove-worktree")
    remove.add_argument("path")
    remove.add_argument("--closed-issue", type=int, help="issue number confirmed closed on GitHub")
    remove.add_argument("--approved-stale", action="store_true", help="the user named this open-issue worktree")
    remove.add_argument("--idle-hours", type=float)
    remove.add_argument("--backup-dir")
    remove.add_argument("--skip-large-untracked", action="store_true")
    remove.add_argument("--yes", action="store_true")
    remove.set_defaults(handler=cmd_remove_worktree)
    aged = commands.add_parser("aged")
    aged.add_argument("key")
    aged.add_argument("--older-than-days", type=float, required=True)
    aged.add_argument("--yes", action="store_true")
    aged.set_defaults(handler=cmd_aged)
    tool = commands.add_parser("tool")
    tool.add_argument("key")
    tool.add_argument("--yes", action="store_true")
    tool.set_defaults(handler=cmd_tool)
    browser = commands.add_parser("browser")
    browser.add_argument("--yes", action="store_true")
    browser.set_defaults(handler=cmd_browser)
    docker = commands.add_parser("docker")
    docker.add_argument("--volumes", action="store_true", help="unused volumes, listed before anything else is removed")
    docker.add_argument("--images", action="store_true", help="unused images and build cache")
    docker.add_argument("--containers", nargs="+", help="stopped containers to remove, by name")
    docker.add_argument("--yes", action="store_true")
    docker.set_defaults(handler=cmd_docker)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except _BadArgumentsExit as error:
        return emit({"ok": False, "code": "bad_args", "summary": error.message, "next": "--help"})
    try:
        return emit(args.handler(args))
    except KeyboardInterrupt:
        return emit({"ok": False, "code": "interrupted", "summary": "Stopped by the user"})


if __name__ == "__main__":
    sys.exit(main())
