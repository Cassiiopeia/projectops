#!/usr/bin/env python3
"""openai-compatible provider — base_url preset swap (#455).

openai/gemini/claude/ollama 모두 OpenAI 호환(/chat/completions). base_url·기본 모델만 다르다.

입력: PROVIDER_NAME(openai|gemini|claude|ollama), CHANGELOG_BASE_URL(ollama용),
      MODEL_API_KEY, COMMIT_RANGE, CHANGELOG_MODEL(선택), CHANGELOG_TEST_RESPONSE(테스트용)
출력: 성공 시 pr_body.md + `PROVIDER=openai:<name>` + exit 0. 실패 시 exit 1 (폴백).
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import collect_commits, write_pr_body, fail  # noqa: E402

# base_url + 기본 모델. 모델명은 **버전을 박지 않고 별칭을 쓴다** — 버전이 박힌 이름은
# 1~2년이면 퇴역한다(실측: gemini-1.5-flash가 404로 죽어 있었다, #566).
# gemini는 lite 별칭이 기본이다. 무료 등급에서 상위 Flash는 RPD 20인 반면 Lite는 500이라
# 자동화에 쓸 수 있는 쪽은 Lite뿐이다(실측).
PRESETS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-flash-lite-latest"),
    "claude": ("https://api.anthropic.com/v1", "claude-3-5-haiku-latest"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "mistral": ("https://api.mistral.ai/v1", "mistral-small-latest"),
    "ollama": (None, "qwen2.5"),  # base_url은 CHANGELOG_BASE_URL 필수
}

PROMPT_TEMPLATE = (
    "다음 커밋들을 사용자용 릴리스 노트로 만들어라. 파일명·prefix·이슈번호·URL 금지. "
    "'새 기능'/'버그 수정'/'개선'으로 분류:\n{commits}"
)


def request_completion(base_url, model, api_key, prompt):
    req_body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=req_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    return data["choices"][0]["message"]["content"]


def main():
    name = os.environ.get("PROVIDER_NAME", "openai")
    if name not in PRESETS:
        fail(f"openai-compatible: 알 수 없는 provider '{name}' — 폴백")
    base_url, default_model = PRESETS[name]
    if name == "ollama":
        base_url = os.environ.get("CHANGELOG_BASE_URL") or None
    model = os.environ.get("CHANGELOG_MODEL") or default_model

    test_response = os.environ.get("CHANGELOG_TEST_RESPONSE")
    if test_response:
        content = test_response
    else:
        if not base_url:
            fail("openai-compatible: base_url 없음 (ollama는 CHANGELOG_BASE_URL 필요) — 폴백")
        commits = collect_commits(os.environ.get("COMMIT_RANGE", "origin/main..HEAD"), limit=40)
        prompt = PROMPT_TEMPLATE.format(commits="\n".join(commits))
        try:
            content = request_completion(base_url, model, os.environ.get("MODEL_API_KEY", ""), prompt)
        except Exception as e:  # 네트워크·인증·파싱 실패 전부 폴백 사유
            fail(f"openai-compatible: API 호출 실패 ({e}) — 폴백")
        if not content or not content.strip():
            fail("openai-compatible: 응답 비어있음 — 폴백")

    write_pr_body(content.strip())
    print(f"PROVIDER=openai:{name}")


if __name__ == "__main__":
    main()
