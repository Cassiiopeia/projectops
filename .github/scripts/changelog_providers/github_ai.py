#!/usr/bin/env python3
"""github-ai provider — ⚠️ 폐기됨 (#566).

GitHub Models가 2026-07-30 완전 종료되어 이 스크립트는 더 이상 동작하지 않는다.
API를 호출하면 HTTP 410이 떨어진다. ladder.py의 사다리에서 제외됐고, 신규 설치
복사 목록에서도 빠졌다. 파일만 남겨둔 이유는 이미 배포된 저장소에 존재하기 때문이며,
호출되지 않으므로 무해하다.

--- 이하 원본 설명 ---

github-ai provider — GitHub Models 추론 API로 릴리스 노트 생성 (#455).

API 키 불필요: 워크플로우 job에 `permissions: models: read`만 있으면 GITHUB_TOKEN으로 동작.
"깔면 바로 작동"의 기본 provider. rate limit·토큰 한도 초과 시 exit 1로 다음 사다리 폴백.

입력: GITHUB_TOKEN(필수), COMMIT_RANGE, CHANGELOG_MODEL(기본 openai/gpt-4o-mini),
      CHANGELOG_TEST_RESPONSE(테스트용)
출력: 성공 시 pr_body.md + `PROVIDER=github-ai` + exit 0. 실패 시 exit 1 (폴백).
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import collect_commits, write_pr_body, fail  # noqa: E402

ENDPOINT = "https://models.github.ai/inference/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

PROMPT_TEMPLATE = (
    "다음 커밋들을 사용자용 릴리스 노트로 만들어라. 파일명·prefix·이슈번호·URL 금지. "
    "'새 기능'/'버그 수정'/'개선'으로 분류:\n{commits}"
)


def request_completion(token, model, prompt):
    req_body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=req_body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    return data["choices"][0]["message"]["content"]


def main():
    test_response = os.environ.get("CHANGELOG_TEST_RESPONSE")
    if test_response:
        content = test_response
    else:
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            fail("github-ai: GITHUB_TOKEN 없음 (permissions: models: read 필요) — 폴백")
        # 입력 토큰 한도(8K) 대응 — 커밋 40개로 제한 (mini 모델 + prefix 필터)
        commits = collect_commits(os.environ.get("COMMIT_RANGE", "origin/main..HEAD"), limit=40)
        model = os.environ.get("CHANGELOG_MODEL") or DEFAULT_MODEL
        prompt = PROMPT_TEMPLATE.format(commits="\n".join(commits))
        try:
            content = request_completion(token, model, prompt)
        except Exception as e:  # rate limit·권한·네트워크 실패 전부 폴백 사유
            fail(f"github-ai: Models API 호출 실패 ({e}) — 폴백")
        if not content or not content.strip():
            fail("github-ai: 응답 비어있음 — 폴백")

    write_pr_body(content.strip())
    print("PROVIDER=github-ai")


if __name__ == "__main__":
    main()
