"""서드파티 GitHub Action 은 커밋 SHA 로 고정한다 (#798).

이 워크플로우들은 남의 저장소에 설치된다. 서드파티 태그(`@v3`)가 옮겨지거나 탈취되면
설치된 모든 저장소에서 그 코드가 시크릿과 함께 실행된다. SHA 는 바뀌지 않는다.

정책: GitHub 이 직접 관리하는 `actions/*` 는 태그를 허용하고, 그 밖의 소유자는 40자 SHA 만 허용한다.
SHA 뒤에는 `# 버전` 주석을 남긴다 (Dependabot 이 이 주석을 보고 갱신한다).
"""
import re
from pathlib import Path

WF = Path(__file__).resolve().parents[3] / ".github" / "workflows"
USES = re.compile(r"^\s*-?\s*uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)@(\S+)(.*)$")
SHA = re.compile(r"^[0-9a-f]{40}$")


def _third_party_refs():
    for path in sorted(WF.rglob("*.y*ml")):
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = USES.match(line)
            if m and not m.group(1).startswith("actions/"):
                yield path, no, m.group(1), m.group(2), m.group(3)


def test_third_party_actions_are_pinned_to_a_sha():
    bad = [f"{p.relative_to(WF)}:{n} {name}@{ref}" for p, n, name, ref, _ in _third_party_refs() if not SHA.match(ref)]
    assert not bad, "태그로만 참조한 서드파티 action (SHA 로 고정할 것):\n" + "\n".join(bad)


def test_pinned_actions_keep_a_version_comment():
    bad = [f"{p.relative_to(WF)}:{n} {name}" for p, n, name, ref, rest in _third_party_refs()
           if SHA.match(ref) and not re.search(r"#\s*v?\d", rest)]
    assert not bad, "SHA 뒤에 `# 버전` 주석이 없다 (Dependabot 갱신·사람의 확인에 필요):\n" + "\n".join(bad)


def test_policy_actually_covers_something():
    assert len(list(_third_party_refs())) > 20, "서드파티 참조를 못 찾았다 — 검사가 헛돌고 있다"
