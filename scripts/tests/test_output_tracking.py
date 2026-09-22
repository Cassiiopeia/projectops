"""산출물 폴더의 추적 여부가 한 곳에서 정해지는지 본다 (#621).

증거물(스크린샷·덤프·렌더)이 조용히 커밋되기 시작하면, 알아챌 때쯤엔 이미
이력에 박혀 있다. 실측으로 어느 레포의 agent-test 폴더가 9.3MB였다.

**분류를 빠뜨린 스킬이 있으면 여기서 막는다.** 규칙이 코드로 강제되지 않으면
스킬이 하나 늘 때마다 새어 나간다.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

from common.paths import (  # noqa: E402
    DOCUMENT_SKILLS, EVIDENCE_SKILLS, ensure_untracked, gitignore_body,
    resolve_output_path,
)


def _declared_skill_ids() -> set[str]:
    """스킬 CLI 들이 실제로 쓰는 skill_id 를 소스에서 긁는다."""
    found = set()
    pattern = re.compile(r"""resolve_output_path\(\s*["']([a-z0-9-]+)["']""")
    for py in (_ROOT / "skills").glob("pro-*/scripts/*.py"):
        found |= set(pattern.findall(py.read_text(encoding="utf-8")))
    return found


def test_every_skill_that_makes_output_is_classified():
    """새 산출물 스킬은 증거인지 문서인지 반드시 선언해야 한다."""
    known = EVIDENCE_SKILLS | DOCUMENT_SKILLS
    used = _declared_skill_ids()
    assert used, "skill_id 를 하나도 못 찾았다 — 탐지 정규식이 낡았을 수 있다"
    missing = sorted(used - known)
    assert missing == [], (
        f"분류되지 않은 산출물 스킬: {missing}. "
        "common/paths.py 의 EVIDENCE_SKILLS 또는 DOCUMENT_SKILLS 에 넣어라 — "
        "증거물이면 폴더에 .gitignore 가 심어지고, 문서면 추적된다")


def test_a_skill_is_never_both():
    assert EVIDENCE_SKILLS & DOCUMENT_SKILLS == frozenset()


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    return path


def test_evidence_folder_gets_gitignore_document_folder_does_not(tmp_path, monkeypatch):
    """증거는 제외되고 문서는 추적된다. 섞으면 한쪽이 반드시 틀린다."""
    proj = _repo(tmp_path / "proj")
    monkeypatch.chdir(proj)

    ev = resolve_output_path("agent-test", "가")
    assert ev["gitignore"] == "created"
    assert (Path(ev["output_root"]) / "agent-test" / ".gitignore").is_file()

    doc = resolve_output_path("report", "나")
    assert "gitignore" not in doc, "문서 폴더에 추적 제외를 심었다 — 보고서가 사라진다"


def test_evidence_really_is_not_staged_by_git_add_all(tmp_path, monkeypatch):
    """`.gitignore` 가 있다가 아니라, `git add -A` 로도 안 담기는지 본다."""
    proj = _repo(tmp_path / "proj")
    monkeypatch.chdir(proj)
    r = resolve_output_path("figma-verify", "로그인")
    base = Path(r["output_root"]) / "figma-verify"
    (base / "20260101_001_로그인").mkdir(parents=True, exist_ok=True)
    (base / "20260101_001_로그인" / "render.png").write_bytes(b"\x89PNG" + b"0" * 5000)

    subprocess.run(["git", "add", "-A"], cwd=proj, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"],
                            cwd=proj, capture_output=True, text=True, check=True
                            ).stdout.split()
    assert staged == ["docs/projectops/figma-verify/.gitignore"], staged


def test_root_gitignore_is_never_touched(tmp_path, monkeypatch):
    """루트 .gitignore 를 고치면 다른 세션·도구의 규칙과 충돌한다 (#561)."""
    proj = _repo(tmp_path / "proj")
    (proj / ".gitignore").write_text("build/\n", encoding="utf-8")
    monkeypatch.chdir(proj)
    resolve_output_path("agent-test", "가")
    assert (proj / ".gitignore").read_text(encoding="utf-8") == "build/\n"


@pytest.mark.parametrize("skill", sorted(EVIDENCE_SKILLS))
def test_ensure_untracked_is_idempotent_and_keeps_foreign(tmp_path, skill):
    d = tmp_path / skill
    assert ensure_untracked(d, skill) == "created"
    assert ensure_untracked(d, skill) == "already"
    (d / ".gitignore").write_text("남이 쓴 것\n", encoding="utf-8")
    assert ensure_untracked(d, skill) == "kept"
    assert (d / ".gitignore").read_text(encoding="utf-8") == "남이 쓴 것\n"


def test_gitignore_keeps_itself_trackable():
    """`*` 만 쓰면 .gitignore 자신도 무시돼 규칙이 레포에 안 남는다."""
    body = gitignore_body("agent-test").splitlines()
    assert body[-2:] == ["*", "!.gitignore"], body
