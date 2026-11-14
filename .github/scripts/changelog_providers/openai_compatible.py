#!/usr/bin/env python3
"""openai-compatible provider — base_url preset swap (#455).

openai/gemini/claude/ollama are all OpenAI-compatible (/chat/completions). Only base_url and default model differ.

Input: PROVIDER_NAME (openai|gemini|claude|ollama), CHANGELOG_BASE_URL (for ollama),
      MODEL_API_KEY, COMMIT_RANGE, CHANGELOG_MODEL (optional), CHANGELOG_TEST_RESPONSE (for tests)
Output: on success pr_body.md + `PROVIDER=openai:<name>` + exit 0. On failure exit 1 (fallback).
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import collect_commits, release_commit_range, write_pr_body, fail, resolve_language, t  # noqa: E402

# base_url + default model. Model names **use aliases, not pinned versions** — pinned names
# retire within 1-2 years (measured: gemini-1.5-flash was dead with 404, #566).
# gemini defaults to the lite alias. On the free tier the higher Flash has RPD 20 while Lite has 500,
# so only Lite is usable for automation (measured).
PRESETS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-flash-lite-latest"),
    "claude": ("https://api.anthropic.com/v1", "claude-3-5-haiku-latest"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "mistral": ("https://api.mistral.ai/v1", "mistral-small-latest"),
    "ollama": (None, "qwen2.5"),  # base_url requires CHANGELOG_BASE_URL
}

def build_prompt(commits, lang=None):
    """The prompt body lives in the catalog — output language and category names must follow the repo language (#793)."""
    return t("release_notes.prompt.openai", lang or resolve_language(), commits=commits)


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
        fail(f"openai-compatible: unknown provider '{name}' — falling back")
    base_url, default_model = PRESETS[name]
    if name == "ollama":
        base_url = os.environ.get("CHANGELOG_BASE_URL") or None
    model = os.environ.get("CHANGELOG_MODEL") or default_model

    test_response = os.environ.get("CHANGELOG_TEST_RESPONSE")
    if test_response:
        content = test_response
    else:
        if not base_url:
            fail("openai-compatible: no base_url (ollama needs CHANGELOG_BASE_URL) — falling back")
        commits = collect_commits(release_commit_range(), limit=40)
        prompt = build_prompt("\n".join(commits))
        try:
            content = request_completion(base_url, model, os.environ.get("MODEL_API_KEY", ""), prompt)
        except Exception as e:  # network, auth and parse failures are all fallback reasons
            fail(f"openai-compatible: API call failed ({e}) — falling back")
        if not content or not content.strip():
            fail("openai-compatible: empty response — falling back")

    write_pr_body(content.strip())
    print(f"PROVIDER=openai:{name}")


if __name__ == "__main__":
    main()
