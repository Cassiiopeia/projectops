#!/usr/bin/env python3
"""copilot provider — GitHub Copilot CLI로 릴리스 노트 생성 (#566).

GitHub Models 종료 이후, **외부 API 키 없이** GitHub 안에서 릴리스 노트를 만들 수 있는
유일한 경로다. 인증은 워크플로우의 GITHUB_TOKEN을 그대로 쓴다.

워크플로우 요구사항:
  permissions:
    copilot-requests: write      # 이것이 없으면 인증 실패
  steps:
    - run: npm install -g @github/copilot

입력: COMMIT_RANGE (기본 origin/main..HEAD), GITHUB_TOKEN
출력: 성공 시 pr_body.md + stdout `PROVIDER=copilot` + exit 0. 실패 시 exit 1 (폴백).

주의 — 과금 단위가 토큰이 아니라 **요청 수(Premium Request)**다. 실측으로 릴리스 1회에
1 Request를 쓰며, 입력 토큰은 31.7k였다(에이전트 오버헤드 포함). 한도가 빠듯하므로
소진 시 다음 단으로 내려가는 경로를 반드시 유지할 것.
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import collect_commits, write_pr_body, fail, resolve_language, t  # noqa: E402

def build_prompt(commits, lang=None):
    """프롬프트 본문은 카탈로그에 있다 — 출력 언어와 분류 이름이 레포 언어를 따라야 한다 (#793)."""
    return t("release_notes.prompt.copilot", lang or resolve_language(), commits=commits)


def main():
    if not shutil.which("copilot"):
        fail("copilot: CLI not installed (npm install -g @github/copilot) — falling back")
    if not os.environ.get("GITHUB_TOKEN"):
        fail("copilot: no GITHUB_TOKEN (needs permissions: copilot-requests: write) — falling back")

    commits = collect_commits(os.environ.get("COMMIT_RANGE", "origin/main..HEAD"))
    if not commits:
        fail("copilot: no commits to summarize — falling back")

    # --no-ask-user: 자동화에는 되묻는 사람이 없다. 이것이 없으면 입력 대기로 멈춘다.
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
        # 크레딧 소진·권한 부족 등. 사유는 stderr에 남기고 다음 단으로 넘긴다.
        detail = (proc.stderr or "").strip().splitlines()
        fail(f"copilot: run failed (exit {proc.returncode}) {detail[-1] if detail else ''} — falling back")

    content = (proc.stdout or "").strip()
    if not content or "*" not in content:
        fail("copilot: empty response or unexpected format — falling back")

    write_pr_body(content)
    print("PROVIDER=copilot")


if __name__ == "__main__":
    main()
