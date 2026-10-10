"""common/memory.py — 스킬 기억 공통 규칙 (#837).

pro-launch knowledge 와 pro-agent-test note 가 같은 유사도·성적·노출 규칙을 써야 한다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from common import memory  # noqa: E402


def test_overlap_same_key_and_area_rules():
    a = {"area": "web", "key": "asc.login", "how": "x"}
    assert memory.overlap(a, {**a, "how": "전혀 다른 문장"}) == 1.0
    assert memory.overlap(a, {**a, "area": "ios"}) == 0.0


def test_overlap_works_without_key_or_group_for_note_entries():
    a = {"text": "되돌릴 수 없는 동작은 서버가 실패했을 때를 반드시 밟는다 비행기모드"}
    b = {"text": "되돌릴 수 없는 동작은 서버가 실패한 경우와 성공한 경우를 둘 다 밟아야"}
    sc = memory.overlap(a, b, field="text")
    assert 0 < sc < 1


def test_min_words_blocks_one_word_merges():
    """'첫 번째'·'두 번째' 는 고유어가 '번째' 하나라 1.0 이 된다 — 짧은 문장은 합치지 않는다."""
    a, b = {"text": "첫 번째"}, {"text": "두 번째"}
    assert memory.overlap(a, b, field="text") == 1.0
    assert memory.overlap(a, b, field="text", min_words=3) == 0.0


def test_find_similar_splits_merge_and_related():
    entries = [{"text": "약관 동의 목록은 스와이프 여러번 해야 끝까지 간다"},
               {"text": "약관 화면 버튼 위치 바뀜 확인 필요 다른 내용 추가"},
               {"text": "전혀 관계 없는 서버 로그 이야기"}]
    best, rel = memory.find_similar({"text": "약관 동의 목록은 스와이프 여러번 해야 끝까지 간다 진짜로"},
                                    entries, field="text", min_words=3)
    assert best == 0
    best2, rel2 = memory.find_similar({"text": "약관 화면 버튼 위치 새로 추가된 메뉴 정리"},
                                      entries, field="text", min_words=3)
    assert best2 is None and rel2 and rel2[0][0] == 1


def test_stats_defaults_for_legacy_entries():
    """옛 항목(성적 없음)은 0·0·추가한 날로 읽는다."""
    assert memory.stats({"text": "x", "added": "2026-09-17"}) == (0, 0, "2026-09-17")


def test_bump_counts_once_per_day_per_result():
    e = {"text": "x"}
    assert memory.bump(e, "ok", "2026-10-10") is True
    assert memory.bump(e, "ok", "2026-10-10") is False      # 같은 날 반복은 부풀리지 않는다
    assert memory.bump(e, "fail", "2026-10-10") is True
    assert memory.bump(e, "ok", "2026-10-11") is True
    assert (e["ok"], e["fail"], e["last_seen"]) == (2, 1, "2026-10-11")


def test_bump_clears_verify_when_success_leads():
    e = {"text": "x", "verify": True}
    memory.bump(e, "ok", "2026-10-10")
    assert "verify" not in e


def test_needs_verify_stale_or_failing():
    now = "2026-10-10"
    assert memory.needs_verify({"ok": 1, "fail": 1, "last_seen": now}, now)
    assert not memory.needs_verify({"ok": 2, "fail": 1, "last_seen": now}, now)
    assert memory.needs_verify({"ok": 5, "last_seen": "2026-01-01"}, now)       # 90일 넘음
    assert memory.hidden({"ok": 0, "fail": 2})
    assert not memory.hidden({"ok": 1, "fail": 2})


def test_seen_today_gates_once_per_slot(tmp_path):
    f = tmp_path / "seen.json"
    assert memory.seen_today(f, "detect:app", "2026-10-10") is False
    assert memory.seen_today(f, "detect:app", "2026-10-10") is True
    assert memory.seen_today(f, "detect:web", "2026-10-10") is False
    assert memory.seen_today(f, "detect:app", "2026-10-11") is False


def test_launch_knowledge_reuses_common_rules():
    """knowledge.py 는 공통 모듈을 그대로 쓴다 — 두 벌이 갈라지면 같은 지식을 다르게 판정한다."""
    sys.path.insert(0, str(ROOT / "skills" / "pro-launch" / "scripts"))
    import knowledge
    assert knowledge.SIMILAR == memory.SIMILAR and knowledge.RELATED == memory.RELATED
    assert knowledge._GENERIC is memory._GENERIC
