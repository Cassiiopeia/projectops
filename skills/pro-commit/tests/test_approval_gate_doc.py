"""승인 설정을 쓰는 모든 경로가 형식 고정 규칙을 따르는지 문서 수준에서 지킨다 (#864).

승인 키(github.commit / repos[].commit)가 생기면 다음 실행부터 "기존 사용자"(legacy-default → projectops)로
판정된다. 형식을 정한 적 없는 신규 사용자에게 preset 을 함께 적지 않으면, 팀 형식 레포에서 한 번 커밋한 뒤
다른 레포에서 형식이 conventional → projectops 로 바뀐다.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = (ROOT / "references" / "approval-gate.md").read_text(encoding="utf-8")
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}.*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert m, heading
    return m.group(0)


def test_rule_covers_team_sources_and_writes_conventional():
    rule = _section(GATE, "D.")
    for needle in ("team-default", "version.yml", "default", "legacy-default",
                   "skills.pro-commit.preset", '"conventional"'):
        assert needle in rule, needle


def test_every_write_path_references_rule():
    # 승인 키를 쓰는 A(수동 전환)·C(첫 실행)·SKILL.md 의 자연어 토글이 모두 규칙 D 를 가리켜야 한다
    for name in ("A.", "C."):
        assert "Rule D" in _section(GATE, name), name
    assert "Rule D" in GATE[:GATE.index("## A.")]  # 자연어 토글 안내(판정 절)
    assert "approval-gate.md" in SKILL and "Rule D" in SKILL
