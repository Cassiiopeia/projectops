#!/usr/bin/env python3
"""changelog provider 폴백 사다리 오케스트레이터 (#455).

version.yml options.changelog.provider 값에 따라 provider를 순서대로 시도하고,
처음 성공한 provider의 pr_body.md를 남긴다. commit은 AI 무의존 최후 보루.

  provider=commit                    → commit
  provider=copilot                   → copilot → (openai*) → commit
  provider=openai|gemini|claude|ollama → 해당 provider → commit
  provider=commit / 미지정            → commit
    (coderabbit 단계 자체는 워크플로우 Job 1의 요청·폴링이 담당 — 이 사다리에
     도달했다는 것은 이미 CodeRabbit이 무응답이었다는 뜻이라 재시도하지 않는다)
  * openai 단계는 MODEL_API_KEY가 있을 때만 끼운다 (없으면 무의미한 시도)

입력: CHANGELOG_PROVIDER + 각 provider의 환경변수 passthrough
출력: pr_body.md + provider_result.json({provider, attempted, failed, notice})
      + stdout `PROVIDER=<승자>` + exit 0. 전 단계 실패 시 exit 1.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OPENAI_FAMILY = ("openai", "gemini", "claude", "groq", "mistral", "ollama")


def build_rungs(provider):
    """(라벨, 스크립트, 추가 env) 목록 — 시도 순서.

    어느 경로든 마지막은 commit이다. AI·네트워크에 의존하지 않아 항상 완주하므로
    "릴리스 노트가 비는" 상황이 생기지 않는다.

    github-ai는 목록에서 빠졌다 — GitHub Models가 2026-07-30 종료되어 호출하면
    410이 떨어진다(#566). 저장값이 남아 있어도 아래 GONE 처리로 흡수한다.
    """
    commit = ("commit", "commit.py", {})
    copilot = ("copilot", "copilot.py", {})
    has_key = bool(os.environ.get("MODEL_API_KEY"))

    if provider == "commit":
        # 키를 등록하는 행위 자체가 "AI를 쓰겠다"는 의사표시다 (#569).
        # commit은 "AI를 절대 쓰지 않음"이 아니라 "설정하지 않음"의 기본값이므로,
        # 키가 있으면 AI를 먼저 시도한다. AI 없이 돌리려면 키를 등록하지 않으면 된다.
        rungs = []
        if has_key:
            rungs.append(("openai:gemini", "openai_compatible.py", {"PROVIDER_NAME": "gemini"}))
        rungs.append(commit)
        return rungs
    if provider in OPENAI_FAMILY:
        return [(f"openai:{provider}", "openai_compatible.py", {"PROVIDER_NAME": provider}), commit]
    if provider == "copilot":
        rungs = [copilot]
        # Copilot은 요청 수로 과금돼 한도가 빠듯하다. 키가 있으면 그다음 단으로 둔다.
        if has_key:
            rungs.append(("openai:gemini", "openai_compatible.py", {"PROVIDER_NAME": "gemini"}))
        rungs.append(commit)
        return rungs
    # 종료된 provider(github-ai)·coderabbit·미지의 값 → 키가 있으면 외부 AI, 없으면 커밋 분석
    rungs = []
    if has_key:
        rungs.append(("openai:gemini", "openai_compatible.py", {"PROVIDER_NAME": "gemini"}))
    rungs.append(commit)
    return rungs


def run_rung(script, extra_env):
    env = dict(os.environ)
    env.update(extra_env)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, script)],
        env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    # rung의 로그는 그대로 통과시켜 워크플로우 로그에서 사유를 볼 수 있게 한다
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode == 0 and os.path.isfile("pr_body.md")


def main():
    provider = os.environ.get("CHANGELOG_PROVIDER") or "commit"
    if provider == "github-ai":
        # 종료된 서비스 — 저장값이 남은 기존 저장소를 위해 조용히 흡수한다 (#566).
        print("ℹ️ github-ai는 서비스가 종료되어 건너뜁니다 (GitHub Models, 2026-07-30)", file=sys.stderr)
        provider = "commit"
    rungs = build_rungs(provider)
    attempted, failed, winner = [], [], None

    for label, script, extra_env in rungs:
        attempted.append(label)
        print(f"🪜 provider 시도: {label}")
        if run_rung(script, extra_env):
            winner = label
            break
        failed.append(label)
        print(f"↩️ {label} 실패 — 다음 단계로 폴백", file=sys.stderr)

    notice = None
    if winner and failed:
        notice = f"{' → '.join(failed)} 실패 → {winner} 사용"

    with open("provider_result.json", "w", encoding="utf-8") as f:
        json.dump(
            {"provider": winner, "attempted": attempted, "failed": failed, "notice": notice},
            f, ensure_ascii=False,
        )

    if not winner:
        print("❌ 사다리 전 단계 실패 — pr_body.md 생성 불가", file=sys.stderr)
        sys.exit(1)
    print(f"PROVIDER={winner}")


if __name__ == "__main__":
    main()
