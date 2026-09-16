"""changelog provider(.py) 테스트 (#455) — 구 test_commit_provider/test_openai_provider/
test_provider_contract .sh 3종을 pytest로 통합·확장 (ladder 폴백 순서 포함).

실행: python -m pytest .github/scripts/test/test_changelog_providers.py -q
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PROVIDERS = ROOT / ".github" / "scripts" / "changelog_providers"
MANAGER = ROOT / ".github" / "scripts" / "changelog_manager.py"


def run_script(script, cwd, env_extra=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(PROVIDERS / script)],
        cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


@pytest.fixture
def git_repo(tmp_path):
    """feat/fix/docs 커밋이 있는 임시 git 레포."""
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("commit", "-q", "--allow-empty", "-m", "feat: 로그인 기능 추가 #12 https://github.com/x/y/issues/12")
    git("commit", "-q", "--allow-empty", "-m", "fix: 버그 수정 #99")
    git("commit", "-q", "--allow-empty", "-m", "docs: 문서 갱신")
    git("commit", "-q", "--allow-empty", "-m", "chore: 잡일 [skip ci]")
    return tmp_path


def read_body(cwd):
    return (Path(cwd) / "pr_body.md").read_text(encoding="utf-8")


# ── commit provider (안전망) ──────────────────────────────────────────

def test_commit_generates_sections(git_repo):
    r = run_script("commit.py", git_repo, {"COMMIT_RANGE": "HEAD~4..HEAD"})
    assert r.returncode == 0, r.stderr
    assert "PROVIDER=commit" in r.stdout
    body = read_body(git_repo)
    assert "Summary by CodeRabbit" in body
    assert "* **새 기능**" in body
    assert "* **버그 수정**" in body
    assert "* **문서**" in body
    # 정제: 이슈번호·URL 제거, [skip ci] 커밋 제외
    assert "#12" not in body and "#99" not in body
    assert "https://" not in body.replace("coderabbit.ai", "")
    assert "잡일" not in body


def test_commit_survives_bogus_range(git_repo):
    """range가 무효여도 최근 커밋 폴백으로 항상 완주 (안전망 계약)."""
    r = run_script("commit.py", git_repo, {"COMMIT_RANGE": "origin/nonexistent..HEAD"})
    assert r.returncode == 0, r.stderr
    assert "로그인 기능 추가" in read_body(git_repo)


# ── openai-compatible provider ────────────────────────────────────────

def test_openai_test_mode(git_repo):
    r = run_script("openai_compatible.py", git_repo, {
        "PROVIDER_NAME": "openai", "MODEL_API_KEY": "dummy",
        "COMMIT_RANGE": "HEAD~1..HEAD",
        "CHANGELOG_TEST_RESPONSE": "* **새 기능**\n  * 로그인 기능이 추가되었습니다",
    })
    assert r.returncode == 0, r.stderr
    assert "PROVIDER=openai:openai" in r.stdout
    body = read_body(git_repo)
    assert "Summary by CodeRabbit" in body
    assert "로그인 기능이 추가" in body


def test_openai_ollama_without_base_url_fails(git_repo):
    r = run_script("openai_compatible.py", git_repo, {"PROVIDER_NAME": "ollama", "CHANGELOG_BASE_URL": ""})
    assert r.returncode == 1
    assert "base_url" in r.stderr


def test_openai_unknown_provider_fails(git_repo):
    r = run_script("openai_compatible.py", git_repo, {"PROVIDER_NAME": "bogus"})
    assert r.returncode == 1


# ── github-ai provider ────────────────────────────────────────────────

def test_github_ai_test_mode(git_repo):
    r = run_script("github_ai.py", git_repo, {
        "CHANGELOG_TEST_RESPONSE": "* **개선**\n  * 응답 속도가 빨라졌습니다",
    })
    assert r.returncode == 0, r.stderr
    assert "PROVIDER=github-ai" in r.stdout
    assert "응답 속도가 빨라졌" in read_body(git_repo)


def test_github_ai_without_token_fails(git_repo):
    r = run_script("github_ai.py", git_repo, {"GITHUB_TOKEN": ""})
    assert r.returncode == 1
    assert "GITHUB_TOKEN" in r.stderr


# ── ladder (폴백 사다리) ──────────────────────────────────────────────

def read_result(cwd):
    return json.loads((Path(cwd) / "provider_result.json").read_text(encoding="utf-8"))


def test_ladder_commit_direct(git_repo):
    r = run_script("ladder.py", git_repo, {"CHANGELOG_PROVIDER": "commit", "COMMIT_RANGE": "HEAD~4..HEAD"})
    assert r.returncode == 0, r.stderr
    result = read_result(git_repo)
    assert result["provider"] == "commit"
    assert result["failed"] == [] and result["notice"] is None


def test_ladder_retired_github_ai_absorbed(git_repo):
    """저장값이 github-ai(서비스 종료)면 호출하지 않고 곧장 다음 단으로 간다 (#566).

    종전에는 사다리 1단이 github-ai라 매 릴리스마다 죽은 API를 한 번씩 때렸다.
    """
    r = run_script("ladder.py", git_repo, {
        "CHANGELOG_PROVIDER": "github-ai", "GITHUB_TOKEN": "",
        "MODEL_API_KEY": "", "COMMIT_RANGE": "HEAD~4..HEAD",
    })
    assert r.returncode == 0, r.stderr
    result = read_result(git_repo)
    assert result["provider"] == "commit"
    assert "github-ai" not in result["attempted"], "종료된 provider를 호출하면 안 된다"
    assert "새 기능" in read_body(git_repo)  # commit 안전망이 실제 본문 생성


def test_ladder_default_is_commit(git_repo):
    """provider 미지정 → commit 단독. 외부 의존이 기본 경로에 없어야 한다."""
    r = run_script("ladder.py", git_repo, {"COMMIT_RANGE": "HEAD~4..HEAD"})
    assert r.returncode == 0, r.stderr
    result = read_result(git_repo)
    assert result["attempted"] == ["commit"]
    assert result["failed"] == []


def test_ladder_copilot_falls_back(git_repo):
    """copilot CLI가 없는 환경(설치 전·크레딧 소진)에서도 완주한다."""
    r = run_script("ladder.py", git_repo, {
        "CHANGELOG_PROVIDER": "copilot", "MODEL_API_KEY": "",
        "COMMIT_RANGE": "HEAD~4..HEAD",
    })
    assert r.returncode == 0, r.stderr
    result = read_result(git_repo)
    assert result["attempted"][0] == "copilot"
    assert result["provider"] == "commit"
    assert "copilot" in (result["notice"] or "")


def test_ladder_copilot_then_key(git_repo):
    """copilot 실패 + MODEL_API_KEY 있으면 외부 AI를 거쳐 내려간다."""
    r = run_script("ladder.py", git_repo, {
        "CHANGELOG_PROVIDER": "copilot", "MODEL_API_KEY": "dummy",
        "CHANGELOG_TEST_RESPONSE": "* **개선**\n  * 키 경유 응답",
        "COMMIT_RANGE": "HEAD~4..HEAD",
    })
    assert r.returncode == 0, r.stderr
    result = read_result(git_repo)
    assert result["attempted"][:2] == ["copilot", "openai:gemini"]


def test_ladder_openai_family_first(git_repo):
    """명시적 openai 계열 선택 시 해당 provider가 1순위."""
    r = run_script("ladder.py", git_repo, {
        "CHANGELOG_PROVIDER": "gemini",
        "CHANGELOG_TEST_RESPONSE": "* **개선**\n  * 제미니 응답",
    })
    assert r.returncode == 0, r.stderr
    assert read_result(git_repo)["provider"] == "openai:gemini"


def test_ladder_coderabbit_skips_repolling(git_repo):
    """coderabbit 저장값도 사다리에서는 재폴링 없이 곧장 폴백한다 (#566에서 폴링 제거)."""
    r = run_script("ladder.py", git_repo, {
        "CHANGELOG_PROVIDER": "coderabbit", "GITHUB_TOKEN": "",
        "COMMIT_RANGE": "HEAD~4..HEAD",
    })
    assert r.returncode == 0, r.stderr
    result = read_result(git_repo)
    assert "coderabbit" not in result["attempted"]
    assert result["provider"] == "commit"


# ── 계약: 어떤 provider 산출물이든 changelog_manager가 파싱 ───────────

def test_contract_with_changelog_manager(git_repo):
    r = run_script("commit.py", git_repo, {"COMMIT_RANGE": "HEAD~4..HEAD"})
    assert r.returncode == 0, r.stderr

    (git_repo / "CHANGELOG.json").write_text('{"metadata": {}, "releases": []}', encoding="utf-8")
    env = dict(os.environ)
    env.update({
        "VERSION": "9.9.9", "PROJECT_TYPE": "basic", "PROJECT_TYPES": "basic",
        "TODAY": "20260711", "PR_NUMBER": "1", "TIMESTAMP": "2026-07-11 00:00:00",
        "PYTHONIOENCODING": "utf-8",
    })
    r2 = subprocess.run(
        [sys.executable, str(MANAGER), "update-from-summary"],
        cwd=git_repo, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr

    data = json.loads((git_repo / "CHANGELOG.json").read_text(encoding="utf-8"))
    hit = [v for v in data.get("releases", []) if v.get("version") == "9.9.9"]
    assert hit, "9.9.9 릴리스 미기록"
    assert hit[0].get("parsed_changes") or hit[0].get("changes"), "parsed_changes 비어있음"
