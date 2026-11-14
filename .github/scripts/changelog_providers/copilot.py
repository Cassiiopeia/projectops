#!/usr/bin/env python3
"""copilot provider — release notes with the GitHub Copilot CLI (#566).

Since GitHub Models shut down, this is the only path that builds release notes inside GitHub
**without an external API key**. Auth uses the workflow's GITHUB_TOKEN as is.

Workflow requirements:
  permissions:
    copilot-requests: write      # auth fails without this
  steps:
    - run: npm install -g @github/copilot

Input: COMMIT_RANGE (default origin/<PR base>..HEAD, _common.release_commit_range), GITHUB_TOKEN
Output: on success pr_body.md + stdout `PROVIDER=copilot` + exit 0. On failure exit 1 (fallback).

Note — billing is per **request (Premium Request)**, not per token. Measured: one release uses
1 Request with 31.7k input tokens (agent overhead included). The quota is tight, so
always keep the path that drops to the next step when it runs out.
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import collect_commits, release_commit_range, write_pr_body, fail, resolve_language, t  # noqa: E402

def build_prompt(commits, lang=None):
    """The prompt body lives in the catalog — output language and category names must follow the repo language (#793)."""
    return t("release_notes.prompt.copilot", lang or resolve_language(), commits=commits)


def main():
    if not shutil.which("copilot"):
        fail("copilot: CLI not installed (npm install -g @github/copilot) — falling back")
    if not os.environ.get("GITHUB_TOKEN"):
        fail("copilot: no GITHUB_TOKEN (needs permissions: copilot-requests: write) — falling back")

    commits = collect_commits(release_commit_range())
    if not commits:
        fail("copilot: no commits to summarize — falling back")

    # --no-ask-user: automation has nobody to answer questions. Without it, it stalls waiting for input.
    try:
        proc = subprocess.run(
            ["copilot", "-p", build_prompt("\n".join(commits)), "--no-ask-user"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
        )
    except subprocess.TimeoutExpired:
        fail("copilot: response timed out — falling back")
    except OSError as e:
        fail(f"copilot: run failed ({e}) — falling back")

    if proc.returncode != 0:
        # Credits exhausted, insufficient permissions, etc. Log the reason to stderr and move to the next step.
        detail = (proc.stderr or "").strip().splitlines()
        fail(f"copilot: run failed (exit {proc.returncode}) {detail[-1] if detail else ''} — falling back")

    content = (proc.stdout or "").strip()
    if not content or "*" not in content:
        fail("copilot: empty response or unexpected format — falling back")

    write_pr_body(content)
    print("PROVIDER=copilot")


if __name__ == "__main__":
    main()
