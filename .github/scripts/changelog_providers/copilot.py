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
from _common import collect_commits, write_pr_body, fail  # noqa: E402

PROMPT = """아래 커밋들을 릴리스 노트로 요약하라.

규칙:
- 항목당 한 줄, 25자 이내
- 명사형으로 끝낸다
- 파일명·함수명·prefix·이슈번호·URL 금지
- 사용자가 체감하는 변화만 쓴다
- 내부 리팩터링·테스트·문서는 제외
- 비슷한 항목은 하나로 합친다
- 분류당 최대 4개
- 설명·머리말 없이 아래 형식만 출력한다

형식:
**새 기능**
* 설정 진단 기능 추가

**버그 수정**
* 로그가 끊기던 문제 해결

**개선**
* 실행 기록 위치 안내 추가

커밋:
{commits}"""


def main():
    if not shutil.which("copilot"):
        fail("copilot: CLI 미설치 (npm install -g @github/copilot) — 폴백")
    if not os.environ.get("GITHUB_TOKEN"):
        fail("copilot: GITHUB_TOKEN 없음 (permissions: copilot-requests: write 필요) — 폴백")

    commits = collect_commits(os.environ.get("COMMIT_RANGE", "origin/main..HEAD"))
    if not commits:
        fail("copilot: 요약할 커밋 없음 — 폴백")

    # --no-ask-user: 자동화에는 되묻는 사람이 없다. 이것이 없으면 입력 대기로 멈춘다.
    try:
        proc = subprocess.run(
            ["copilot", "-p", PROMPT.format(commits="\n".join(commits)), "--no-ask-user"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
        )
    except subprocess.TimeoutExpired:
        fail("copilot: 응답 시간 초과 — 폴백")
    except OSError as e:
        fail(f"copilot: 실행 실패 ({e}) — 폴백")

    if proc.returncode != 0:
        # 크레딧 소진·권한 부족 등. 사유는 stderr에 남기고 다음 단으로 넘긴다.
        detail = (proc.stderr or "").strip().splitlines()
        fail(f"copilot: 실행 실패 (exit {proc.returncode}) {detail[-1] if detail else ''} — 폴백")

    content = (proc.stdout or "").strip()
    if not content or "*" not in content:
        fail("copilot: 응답이 비었거나 형식 불일치 — 폴백")

    write_pr_body(content)
    print("PROVIDER=copilot")


if __name__ == "__main__":
    main()
