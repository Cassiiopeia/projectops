"""댓글 트리거 오발동 방지 (#576).

실사고: SUH-ISSUE-HELPER가 새 이슈에 다는 안내문에 사용법으로 `@projectops app build`가
적혀 있었고, 앱 빌드 트리거의 조건이 "댓글에 그 단어들이 있는가"만 봤다.
**projectops가 만든 안내문이 projectops가 만든 트리거를 불렀다.**
이슈를 만들기만 해도 빌드가 돌고, 브랜치가 없으니 실패 댓글이 달렸다.

두 축을 함께 지킨다.
  ① 안내문은 마커로 시작한다 (트리거가 걸러낼 수 있어야 한다)
  ② 댓글 기반 트리거는 그 마커를 제외한다
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"
MARKER = "<!-- SUH-ISSUE-HELPER -->"

sys.path.insert(0, str(ROOT / ".github" / "scripts"))
import issue_helper as ih  # noqa: E402


def comment_trigger_workflows():
    """댓글 본문을 조건으로 쓰는 워크플로우 — 새로 생겨도 자동으로 잡힌다."""
    found = []
    for p in WF.rglob("*.y*ml"):
        text = p.read_text(encoding="utf-8")
        if "github.event.comment.body" in text and re.search(r"^\s*if:", text, re.M):
            found.append(p)
    return found


class TestGuideIsMarked:
    """① 안내문은 걸러낼 수 있어야 한다."""

    def test_comment_starts_with_marker(self):
        cfg = {"comment_marker": MARKER, "show_guide": True}
        body = ih.build_comment_body(cfg, "20260917_#1_제목", "커밋 메시지", "안내 본문")
        assert body.startswith(MARKER), "마커가 맨 앞에 없으면 트리거가 걸러낼 수 없다"

    def test_marker_present_even_without_guide(self):
        cfg = {"comment_marker": MARKER, "show_guide": False}
        body = ih.build_comment_body(cfg, "20260917_#1_제목", "커밋 메시지", "")
        assert MARKER in body


class TestTriggersExcludeMarker:
    """② 댓글 트리거는 봇 안내문에 반응하지 않는다."""

    @pytest.mark.parametrize("path", comment_trigger_workflows(), ids=lambda p: p.name)
    def test_trigger_guards_against_helper_comment(self, path):
        text = path.read_text(encoding="utf-8")
        # PR 프리뷰처럼 여러 조건이 있는 파일은 '@projectops'를 보는 자리마다 가드가 필요하다.
        if "@projectops" not in text:
            pytest.skip("멘션 기반 트리거가 아님")
        assert f"!contains(github.event.comment.body, '{MARKER}')" in text, (
            f"{path.name}: 봇 안내 댓글을 제외하지 않는다 — 안내문 문구가 조건을 만족하면 오발동한다"
        )


class TestGuideDoesNotArmOtherTriggers:
    """안내문이 다른 트리거의 조건까지 만족하는지 — 늘어날 때마다 확인한다."""

    def _guide(self, tmp_path):
        wf = tmp_path / "workflows"
        wf.mkdir()
        # GUIDE_LINES가 파일 실존을 보므로 전부 만들어 최대 안내문을 얻는다
        for fname, _ in ih.GUIDE_LINES:
            (wf / fname).write_text("name: t\n", encoding="utf-8")
        return ih.build_guide(wf)

    def test_guide_contains_app_build_words(self, tmp_path):
        """현실 확인 — 실제로 조건을 만족하는 문구가 들어 있다."""
        g = self._guide(tmp_path)
        assert "@projectops" in g and "app" in g and "build" in g, (
            "이 조합이 사라졌다면 좋지만, 가드를 걷어내도 된다는 뜻은 아니다"
        )

    def test_full_comment_is_still_filtered(self, tmp_path):
        """안내문이 조건을 만족해도 마커 덕분에 걸러진다."""
        cfg = {"comment_marker": MARKER, "show_guide": True}
        body = ih.build_comment_body(cfg, "20260917_#1_제목", "커밋", self._guide(tmp_path))
        armed = "@projectops" in body and "app" in body and "build" in body
        assert armed, "조건을 만족하는 것이 사고의 전제였다"
        assert MARKER in body, "그럼에도 마커가 있어 트리거가 걸러낸다"


class TestHumanCommentsStillWork:
    """사람이 직접 다는 댓글에는 마커가 없다 — 기존 동작 보존."""

    @pytest.mark.parametrize("body", [
        "@projectops app build",
        "@projectops apk build",
        "@projectops ios build",
        "@projectops create qa",
    ])
    def test_human_comment_has_no_marker(self, body):
        assert MARKER not in body

class TestInlineNotIsYamlSafe:
    """인라인 `if: !contains(...)`는 YAML이 `!`를 태그 지시자로 읽어 파싱에 실패한다.

    실사고: #576을 고치면서 PR Preview 두 파일에 인라인 `!`를 넣었다가 파싱이 깨질 뻔했다.
    블록 스칼라(`if: |`) 안에서는 안전하지만, 한 줄 `if:`에 쓰려면 `${{ }}`로 감싸야 한다.
    """

    @pytest.mark.parametrize("path", comment_trigger_workflows(), ids=lambda p: p.name)
    def test_every_inline_if_parses(self, path):
        import re
        import yaml

        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^\s*if: (?!\|)(.+)$", text, re.M):
            line = m.group(0).strip()
            lineno = text[:m.start()].count("\n") + 1
            try:
                yaml.safe_load(line + "\n")
            except Exception as e:  # noqa: BLE001
                pytest.fail(
                    f"{path.name}:{lineno} 인라인 if가 YAML로 파싱되지 않는다 — "
                    f"`!`로 시작하면 ${{{{ }}}}로 감쌀 것. ({type(e).__name__})"
                )
