"""워크플로우 토큰 권한 선언 (#595).

실사고: `@projectops apk build` 로 만든 테스트 빌드가 **항상 실패**했다.
빌드 워크플로우에 `permissions:` 블록이 없어 레포 기본값을 따랐는데,
GitHub 신규 레포 기본값이 `read` 라서 진행 상황 댓글을 다는 순간 막혔다.

    RequestError [HttpError]: Resource not accessible by integration

트리거 워크플로우에는 블록이 있어 **트리거까지는 성공**했다. 그래서 겉보기에는
"빌드가 도는데 결과가 없다"로 보였고 원인을 찾는 데 오래 걸렸다.

선언하지 않으면 두 방향 모두 위험하다.
  기본값이 read  → 쓰기가 필요한 워크플로우가 실패한다 (위 사고)
  기본값이 write → 읽기만 하면 되는 배포 워크플로우가 과한 권한을 갖는다

그래서 **모든 워크플로우가 명시**하는 것을 규칙으로 둔다.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"

# GITHUB_TOKEN 으로 쓰기를 하는 호출. 있으면 read 권한만으로는 반드시 실패한다.
_WRITES_ISSUE = re.compile(
    r"createComment|updateComment|deleteComment|issues\.create\b|issues\.update\b"
    r"|addLabels|setLabels|removeLabel", re.I)


def workflows():
    return sorted(WF.rglob("*.y*ml"))


def _load(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _declared(doc: dict) -> bool:
    """최상위 또는 job 단위 어느 쪽에 선언해도 인정한다."""
    if "permissions" in doc:
        return True
    jobs = doc.get("jobs") or {}
    return bool(jobs) and all("permissions" in (j or {}) for j in jobs.values())


@pytest.mark.parametrize("path", workflows(), ids=lambda p: p.name)
def test_every_workflow_declares_permissions(path):
    """레포 기본값에 기대지 않는다 — 기본값은 레포마다 다르고 나중에 바뀐다."""
    assert _declared(_load(path)), (
        f"{path.relative_to(WF)} 에 permissions 선언이 없다. "
        "읽기만 하면 `contents: read`, 댓글을 달면 `issues: write` 를 명시하라"
    )


# 이슈 쪽에서 출발하는 트리거. 여기서 단 댓글은 **이슈 댓글**이라 issues: write 가 있어야
# 한다. PR 에 다는 댓글은 같은 API(issues.createComment)를 쓰지만 pull-requests: write
# 로 충분하다 — 둘을 구분하지 않으면 멀쩡한 CI 를 실패로 잡는다.
_ISSUE_EVENTS = {"issues", "issue_comment", "repository_dispatch"}


def _scopes(doc: dict) -> dict:
    scopes = dict(doc.get("permissions") or {})
    for job in (doc.get("jobs") or {}).values():
        scopes.update((job or {}).get("permissions") or {})
    return scopes


def _comment_writer(path: Path):
    """댓글을 쓰는 워크플로우면 (doc, scopes) 를, 아니면 None 을 준다."""
    text = path.read_text(encoding="utf-8")
    if not _WRITES_ISSUE.search(text):
        return None
    # 별도 PAT로 부르면 GITHUB_TOKEN 권한과 무관하다
    if re.search(r"github-token:\s*\$\{\{\s*secrets\.(?!GITHUB_TOKEN)", text):
        return None
    doc = _load(path)
    return doc, _scopes(doc)


@pytest.mark.parametrize("path", workflows(), ids=lambda p: p.name)
def test_comment_writing_workflows_can_write(path):
    """댓글을 다는데 쓰기 권한이 하나도 없으면 그 스텝에서 반드시 죽는다."""
    got = _comment_writer(path)
    if got is None:
        pytest.skip("이 워크플로우는 GITHUB_TOKEN 으로 댓글을 쓰지 않는다")
    _, scopes = got
    assert "write" in (scopes.get("issues"), scopes.get("pull-requests")), (
        f"{path.relative_to(WF)} 는 댓글을 다는데 쓰기 권한이 없다 "
        f"(현재: {scopes or '선언 없음'})"
    )


@pytest.mark.parametrize("path", workflows(), ids=lambda p: p.name)
def test_issue_triggered_workflows_have_issues_write(path):
    """이슈에서 출발한 워크플로우가 다는 댓글은 이슈 댓글이다.

    실사고가 정확히 이 자리였다 — repository_dispatch 로 돌면서 이슈에 진행 상황을
    남기는데 issues: write 가 없어 첫 댓글에서 멈췄다.
    """
    got = _comment_writer(path)
    if got is None:
        pytest.skip("이 워크플로우는 GITHUB_TOKEN 으로 댓글을 쓰지 않는다")
    doc, scopes = got
    events = doc.get(True) or doc.get("on") or {}      # PyYAML 이 on: 을 True 로 읽는다
    names = set(events) if isinstance(events, dict) else {events} if isinstance(events, str) else set(events or [])
    if not (names & _ISSUE_EVENTS):
        pytest.skip("이슈에서 출발하지 않는다")
    assert scopes.get("issues") == "write", (
        f"{path.relative_to(WF)} 는 이슈 댓글을 다는데 issues: write 가 없다 "
        f"(현재: {scopes or '선언 없음'})"
    )
