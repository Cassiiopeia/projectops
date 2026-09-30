"""앱 빌드 댓글 트리거의 작성자 권한 검사 (#645).

공개 저장소에서는 누구나 댓글을 달 수 있다. 검사가 없으면 낯선 사람의 댓글 한 줄이
서명 키와 스토어 시크릿이 들어가는 빌드를 깨운다.

⚠️ permissions.contents 는 write 로 유지해야 한다. 이 워크플로는 GITHUB_TOKEN 으로
repos.createDispatchEvent 를 호출하고, 그 API 는 contents: write 를 요구한다.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows" / "project-types" / "flutter" / "PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml"
MARKER = "<!-- SUH-ISSUE-HELPER -->"


def _if_condition() -> str:
    data = yaml.safe_load(WF.read_text(encoding="utf-8"))
    return data["jobs"]["trigger-builds"]["if"]


def test_if_checks_author_association():
    assert "github.event.comment.author_association" in _if_condition()


def test_default_allowlist_has_trusted_roles():
    cond = _if_condition()
    m = re.search(r"fromJSON\([^)]*?'(\[[^']*\])'\)", cond)
    assert m, "기본 허용 목록(JSON 배열 리터럴)이 없다"
    for role in ("OWNER", "MEMBER", "COLLABORATOR"):
        assert f'"{role}"' in m.group(1)
    assert "CONTRIBUTOR" not in m.group(1), "기본값에 외부 기여자를 넣지 않는다"


def test_private_repo_is_exempt():
    assert "github.event.repository.private == true" in _if_condition()


def test_allowlist_overridable_by_variable():
    assert "vars.PROJECTOPS_TRIGGER_ASSOCIATIONS" in _if_condition()


def test_bot_marker_guard_and_keywords_remain():
    cond = _if_condition()
    assert f"!contains(github.event.comment.body, '{MARKER}')" in cond
    assert "contains(github.event.comment.body, '@projectops')" in cond
    assert "'apk'" in cond and "'ios'" in cond


def test_contents_permission_stays_write():
    data = yaml.safe_load(WF.read_text(encoding="utf-8"))
    assert data["permissions"]["contents"] == "write"
