#!/usr/bin/env python3
"""릴리스 노트 생성 결과 안내 (#566) — stdlib 전용.

두 곳에 나눠 알린다. 목적이 다르기 때문이다.

  Job Summary : 매번. 어떤 경로로 만들어졌는지 기록. **이메일 알림이 가지 않는다.**
  PR 댓글     : AI를 하나도 쓰지 못했을 때만. 품질이 실제로 떨어진 경우다.

"잘 돌아갔는데 경로만 바뀐 것"(copilot 소진 → 외부 AI 성공)은 알리지 않는다.
매 릴리스마다 댓글이 오면 소음이 되고, 소음이 되면 아무도 읽지 않는다.

댓글은 마커로 기존 것을 찾아 **갱신**한다. GitHub은 댓글 수정에 알림을 보내지 않으므로
이메일은 처음 한 번만 간다.

사용:
  changelog_notice.py --repo owner/name --pr 12 --result provider_result.json
환경: GITHUB_TOKEN(댓글 작성), GITHUB_STEP_SUMMARY(요약 기록 위치)
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

MARKER = "<!-- PROJECTOPS-CHANGELOG-NOTICE -->"
API = "https://api.github.com"

# 사람이 읽는 이름 — 내부 라벨을 그대로 보여주지 않는다
LABELS = {
    "copilot": "Copilot",
    "commit": "커밋 내용 분석",
    "openai:gemini": "Gemini",
    "openai:openai": "OpenAI",
    "openai:claude": "Claude",
    "openai:groq": "Groq",
    "openai:mistral": "Mistral",
    "openai:ollama": "Ollama",
}


def label(name):
    return LABELS.get(name, name)


def build_summary(result):
    """Job Summary용 마크다운 — 어떤 경로를 거쳤는지 한눈에."""
    winner = result.get("provider")
    attempted = result.get("attempted") or []
    failed = set(result.get("failed") or [])

    lines = ["## 릴리스 노트 생성 결과", "", "| 단계 | 결과 |", "|---|---|"]
    for name in attempted:
        mark = "✅ 사용됨" if name == winner else ("❌ 실패" if name in failed else "—")
        lines.append(f"| {label(name)} | {mark} |")
    if not attempted:
        lines.append("| — | 생성 단계가 실행되지 않음 |")
    lines += ["", f"**최종: {label(winner) if winner else '생성 실패'}**", ""]
    return "\n".join(lines)


def build_comment(result):
    """PR 댓글용 — AI를 하나도 못 썼을 때만. 없으면 None."""
    if result.get("provider") != "commit":
        return None
    failed = result.get("failed") or []
    if not failed:
        # 처음부터 commit만 시도한 경우(설정대로 동작) — 알릴 것이 없다
        return None

    tried = ", ".join(label(f) for f in failed)
    return "\n".join([
        MARKER,
        "",
        "### 릴리스 노트를 커밋 내용으로 정리했습니다",
        "",
        f"AI 요약을 시도했으나 사용하지 못했습니다 (시도: {tried}).",
        "릴리스는 정상 진행되며, 아래 중 하나로 품질을 올릴 수 있습니다.",
        "",
        "**① 무료 AI 키 등록** (2분, 신용카드 불필요)",
        "",
        "1. https://aistudio.google.com/apikey 에서 키 발급",
        "2. Settings → Secrets and variables → Actions → New repository secret",
        "3. 이름 `MODEL_API_KEY`, 값은 발급받은 키",
        "",
        "**② 직접 작성**",
        "",
        "이 PR 본문에 릴리스 노트를 쓰면 그대로 사용됩니다. 자동 생성은 건너뜁니다.",
        "",
        "---",
        "",
        "<sub>이 안내는 같은 댓글을 갱신하므로 릴리스마다 새로 쌓이지 않습니다.</sub>",
    ])


def request(method, url, token, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp) if resp.length != 0 else None


def upsert_comment(repo, pr, token, body):
    """마커가 있는 기존 댓글을 찾아 갱신, 없으면 생성."""
    try:
        comments = request("GET", f"{API}/repos/{repo}/issues/{pr}/comments?per_page=100", token) or []
    except urllib.error.URLError as e:
        print(f"⚠️ 댓글 조회 실패 ({e}) — 안내를 건너뜁니다", file=sys.stderr)
        return
    existing = next((c for c in comments if MARKER in (c.get("body") or "")), None)
    try:
        if existing:
            request("PATCH", f"{API}/repos/{repo}/issues/comments/{existing['id']}", token, {"body": body})
            print(f"📝 안내 댓글 갱신 (#{existing['id']}) — 알림은 가지 않습니다")
        else:
            request("POST", f"{API}/repos/{repo}/issues/{pr}/comments", token, {"body": body})
            print("📣 안내 댓글 작성")
    except urllib.error.URLError as e:
        print(f"⚠️ 댓글 작성 실패 ({e}) — 릴리스는 계속됩니다", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--result", default="provider_result.json")
    args = ap.parse_args()

    try:
        with open(args.result, encoding="utf-8") as f:
            result = json.load(f)
    except (OSError, ValueError) as e:
        print(f"⚠️ 결과 파일을 읽지 못했습니다 ({e})", file=sys.stderr)
        return 0  # 안내 실패가 릴리스를 막아선 안 된다

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(build_summary(result) + "\n")
        except OSError as e:
            print(f"⚠️ Job Summary 기록 실패 ({e})", file=sys.stderr)
    else:
        print(build_summary(result))

    body = build_comment(result)
    token = os.environ.get("GITHUB_TOKEN")
    if body and token:
        upsert_comment(args.repo, args.pr, token, body)
    elif body:
        print("ℹ️ GITHUB_TOKEN 없음 — 안내 댓글을 건너뜁니다", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
