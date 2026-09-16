"""릴리스 노트 입력 경로 — 워킹트리 오염 방지 (#564).

실사고: 워크플로우가 artifact를 저장소 루트에 풀었고, 릴리스 커밋의 `git add -A`가
그 임시 파일(pr_body.md)을 함께 커밋했다. v4.4.1부터 매 릴리스마다 반복됐고
이 템플릿을 쓰는 모든 저장소에서 같은 일이 벌어졌다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "changelog_manager.py"

BODY = """<!-- auto -->
## Summary by CodeRabbit
## 릴리스 노트

* **새 기능**
  * 외부 경로 입력 지원

<!-- end -->
"""


def run(cwd, env_extra):
    env = {**os.environ, "VERSION": "1.0.0", "PROJECT_TYPES": "node", "TODAY": "2026-09-16",
           "PR_NUMBER": "1", "TIMESTAMP": "2026-09-16T00:00:00Z", "PYTHONIOENCODING": "utf-8"}
    env.update(env_extra)
    return subprocess.run([sys.executable, str(SCRIPT), "update-from-summary"],
                          cwd=cwd, env=env, capture_output=True, text=True)


@pytest.fixture
def work(tmp_path):
    return tmp_path / "repo"


def test_reads_from_env_path_outside_worktree(work, tmp_path):
    """PR_BODY_PATH가 가리키는 워킹트리 밖 파일을 읽는다."""
    work.mkdir()
    external = tmp_path / "runner_temp" / "pr_body.md"
    external.parent.mkdir(parents=True)
    external.write_text(BODY, encoding="utf-8")

    r = run(work, {"PR_BODY_PATH": str(external)})
    assert r.returncode == 0, r.stderr
    assert "외부 경로 입력 지원" in json.dumps(
        json.loads((work / "CHANGELOG.json").read_text(encoding="utf-8")), ensure_ascii=False)


def test_does_not_create_file_in_worktree(work, tmp_path):
    """읽기만 하고 워킹트리에 임시 파일을 남기지 않는다 — 이것이 오염의 원인이었다."""
    work.mkdir()
    external = tmp_path / "runner_temp" / "pr_body.md"
    external.parent.mkdir(parents=True)
    external.write_text(BODY, encoding="utf-8")

    run(work, {"PR_BODY_PATH": str(external)})
    assert not (work / "pr_body.md").exists(), "워킹트리에 pr_body.md가 생기면 릴리스 커밋에 딸려간다"


def test_falls_back_to_cwd_when_env_absent(work):
    """env가 없으면 종전처럼 cwd에서 찾는다 (하위호환)."""
    work.mkdir()
    (work / "pr_body.md").write_text(BODY, encoding="utf-8")

    r = run(work, {})
    assert r.returncode == 0, r.stderr
    assert (work / "CHANGELOG.json").exists()


def test_missing_input_lists_checked_paths(work):
    """입력이 없으면 어디를 봤는지 알려준다 — 원인 추적이 되어야 한다."""
    work.mkdir()
    r = run(work, {"PR_BODY_PATH": str(work / "nowhere.md")})
    assert r.returncode == 1
    assert "nowhere.md" in r.stdout or "nowhere.md" in r.stderr
