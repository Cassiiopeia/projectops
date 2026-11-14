#!/usr/bin/env python3
"""
dispatch_downstream.py

When a release PR is merged with the default token (GITHUB_TOKEN), explicitly wake the follow-up workflows
that should have run on the base branch push (issue #551).

Why: GitHub does not re-trigger workflows from pushes made by GITHUB_TOKEN
(prevents infinite loops). Merging with a PAT has no such limit, so this script is not needed then.
workflow_dispatch events, however, can be triggered with GITHUB_TOKEN — this uses that.

Targets are found among workflows actually installed in the repo, not a fixed list, because
deploy workflows differ per project type. Both conditions must hold to wake one:
  1) triggered by a push to the base branch  — should it have run?
  2) supports workflow_dispatch              — is there a way to wake it?

Without 2) there is no way to wake it. Instead of skipping silently, print the name so the user decides.

  - Commands: scan | dispatch
  - Output: always JSON (ok / data / next)

Usage:
  python3 dispatch_downstream.py scan --branch main
  GITHUB_TOKEN=... python3 dispatch_downstream.py dispatch --repo owner/name --branch main
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
from pathlib import Path

import github_api
from i18n.messages import t as message

WORKFLOWS_DIR = Path(".github/workflows")

# This workflow itself runs on the release PR event, so it is not a push target. Even if renamed it is
# filtered by the trigger check below (push+branch), but the intent is recorded.
SELF = "PROJECT-COMMON-RELEASE-CHANGELOG"

# Workflows that must not be woken — they rightly run on push but are harmful "right after a release merge".
#
# VERSION-CONTROL: a safety net that must fire only on "a direct main push that skipped the release PR".
#   Waking it after a release merge directly contradicts its design. Its guard checks only
#   HEAD^..HEAD when github.event.before is missing, and dispatch has no before.
#   If a follow-up commit such as the README update lands first, that range has no version.yml, the guard leaks
#   and the version goes up once more. Exclude it outright instead of relying on order.
EXCLUDE = {"PROJECT-COMMON-VERSION-CONTROL"}
USER_AGENT = "projectops-dispatch-downstream"


def _strip_comments(text: str) -> str:
    """Remove comment lines — so example triggers in comments are not mistaken for real ones."""
    return "\n".join(l for l in text.split("\n") if not re.match(r"^\s*#", l))


def parse_triggers(text: str, branch: str) -> dict:
    """Extract only the needed trigger info from workflow YAML.

    Why no real YAML parser: workflows in this repo contain 0-indent heredocs that make
    strict parsers fail (GitHub itself handles them). Only the trigger block matters here, so
    a line-by-line scan is safer.
    """
    body = _strip_comments(text)
    lines = body.split("\n")

    has_dispatch = any(re.match(r"^\s*workflow_dispatch:", l) for l in lines)

    # Find the branches list under push: inside the on: block (3 forms: ["x"] / newline "- x" / single value x)
    in_on = False
    in_push = False
    in_branch_list = False
    has_branches_key = False
    push_branches: list[str] = []
    for line in lines:
        if re.match(r"^on:", line):
            in_on = True
            continue
        if in_on and re.match(r"^[a-zA-Z_]", line):  # another top-level key -> end of on block
            in_on = False
            in_push = False
        if not in_on:
            continue
        if re.match(r"^\s{2}push:", line):
            in_push = True
            continue
        if in_push and re.match(r"^\s{2}[a-zA-Z_]+:", line):  # another event at the same depth as push
            in_push = False
        if not in_push:
            in_branch_list = False
            continue
        # Newline list: "- x" on the lines after branches:
        if in_branch_list:
            item = re.match(r"^\s+-\s*[\"']?([^\"'\s#]+)", line)
            if item:
                push_branches.append(item.group(1))
                continue
            if line.strip():
                in_branch_list = False
        key = re.match(r"^\s+branches:\s*(.*?)\s*$", line)
        if not key:
            continue
        has_branches_key = True
        value = key.group(1)
        inline = re.match(r"^\[(.*?)\]", value)
        if inline:
            push_branches += [b.strip().strip("\"'") for b in inline.group(1).split(",") if b.strip()]
        elif value == "":
            in_branch_list = True
        else:
            push_branches.append(value.strip("\"'"))

    return {
        "workflow_dispatch": has_dispatch,
        "push_branches": push_branches,
        "on_push_branch": branch in push_branches,
        # branches: present but value unreadable — report as unreachable so it does not drop silently
        "branches_unreadable": has_branches_key and not push_branches,
    }


def scan(branch: str, workflows_dir: Path = WORKFLOWS_DIR) -> dict:
    """Scan installed workflows and split them into wake targets and unwakeable ones."""
    targets, unreachable = [], []
    if workflows_dir.is_dir():
        for path in sorted(workflows_dir.iterdir()):
            if not path.is_file() or path.suffix not in (".yaml", ".yml"):
                continue
            if path.stem == SELF or path.stem in EXCLUDE:
                continue
            try:
                info = parse_triggers(path.read_text(encoding="utf-8"), branch)
            except Exception as e:
                # Undecidable — do not wake, but keep it in the result to surface for manual checking
                sys.stderr.write(f"  ⚠️ Could not read triggers: {path.name} ({type(e).__name__}: {e})\n")
                unreachable.append(path.name)
                continue
            if info["branches_unreadable"]:
                sys.stderr.write(f"  ⚠️ Could not read push.branches: {path.name}\n")
                unreachable.append(path.name)
                continue
            if not info["on_push_branch"]:
                continue
            (targets if info["workflow_dispatch"] else unreachable).append(path.name)
    return {"targets": targets, "unreachable": unreachable}


def _dispatch_one(repo: str, token: str, filename: str, ref: str) -> tuple[bool, str]:
    url = f"{github_api.API_ROOT}/repos/{repo}/actions/workflows/{filename}/dispatches"
    try:
        status, _ = github_api.send("POST", url, token, {"ref": ref}, user_agent=USER_AGENT)
        return (200 <= status < 300), f"HTTP {status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} {e.reason}"
    except Exception as e:  # network errors etc. — never fail the release itself
        return False, f"{type(e).__name__}: {e}"


def _notify_pr(repo: str, pr: str, token: str, out: dict) -> None:
    """Notify the release PR when every dispatch fails (#555).

    In repos without a PAT, dispatch is the only way to wake follow-up workflows. If all fail,
    deploy and sync are skipped entirely, and a log alone goes unnoticed.
    """
    if not (repo and pr and token):
        return
    try:
        github_api.request("POST", f"{github_api.API_ROOT}/repos/{repo}/issues/{pr}/comments",
                           token, {"body": render_failure_comment(out)}, user_agent=USER_AGENT)
        sys.stderr.write("  ℹ️ Reported the failure on the release PR\n")
    except Exception as e:  # a failed notification must not block the release
        sys.stderr.write(f"  ⚠️ Could not comment on the PR: {type(e).__name__}\n")


def render_failure_comment(out: dict, lang: str | None = None) -> str:
    """All-failed notification body: title > guidance > failure table > what to check. Language from version.yml options.language (#769)"""
    lines = [
        message("dispatch.comment.title", lang),
        "",
        message("dispatch.comment.intro", lang),
        "",
        f"| {message('dispatch.comment.col_workflow', lang)} | {message('dispatch.comment.col_reason', lang)} |",
        "|---|---|",
    ]
    for item in out.get("failed", []):
        lines.append(f"| `{item['workflow']}` | {item['detail']} |")
    lines += [
        "",
        message("dispatch.comment.check_heading", lang),
        message("dispatch.comment.check_permissions", lang),
        message("dispatch.comment.check_manual_run", lang),
    ]
    return "\n".join(lines)


def _log(out: dict) -> None:
    """Write the result to stderr in plain words so it reads directly in the Actions log."""
    w = sys.stderr.write
    for item in out.get("dispatched", []):
        w(f"  ✅ Triggered: {item['workflow']}\n")
    for item in out.get("failed", []):
        w(f"  ⚠️ Trigger failed: {item['workflow']} ({item['detail']})\n")
    for name in out.get("unreachable", []):
        w(f"  ⚠️ Cannot trigger (no workflow_dispatch, or triggers unreadable): {name}\n")
        w("     Without a PAT this workflow does not run automatically after a release.\n")
    w(f"{out.get('summary', '')}\n")


def cmd_scan(args) -> int:
    result = scan(args.branch)
    result["ok"] = True
    result["summary"] = f"{len(result['targets'])} to trigger / {len(result['unreachable'])} cannot be triggered"
    result["next"] = "dispatch" if result["targets"] else None
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_dispatch(args) -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    found = scan(args.branch)
    dispatched, failed = [], []

    if not token:
        out = {"ok": False, "code": "missing_token", "dispatched": [], "failed": [],
               "unreachable": found["unreachable"],
               "summary": "No GITHUB_TOKEN, follow-up workflows were not triggered", "next": None}
        _log(out)
        print(json.dumps(out, ensure_ascii=False))
        return 0  # the release is already done — do not block the pipeline with a failure here

    for filename in found["targets"]:
        ok, detail = _dispatch_one(args.repo, token, filename, args.branch)
        (dispatched if ok else failed).append({"workflow": filename, "detail": detail})

    out = {
        "ok": not failed,
        "dispatched": dispatched,
        "failed": failed,
        "unreachable": found["unreachable"],
        "summary": f"{len(dispatched)} triggered / {len(failed)} failed / {len(found['unreachable'])} cannot be triggered",
        "next": None,
    }
    # Human-readable logs go to stderr — keeps the contract that stdout is one JSON line.
    _log(out)
    # If nothing could be woken, do not pass silently (#555)
    if failed and not dispatched:
        _notify_pr(args.repo, os.environ.get("PR_NUMBER", ""), token, out)
    print(json.dumps(out, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dispatch_downstream")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="find follow-up workflows to wake (no network)")
    p_scan.add_argument("--branch", required=True, help="base branch (e.g. main)")

    p_dispatch = sub.add_parser("dispatch", help="scan, then trigger workflow_dispatch")
    p_dispatch.add_argument("--repo", required=True, help="owner/name")
    p_dispatch.add_argument("--branch", required=True, help="base branch (e.g. main)")

    args = parser.parse_args(argv)
    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "dispatch":
        return cmd_dispatch(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
