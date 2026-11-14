"""Workflow token permission declarations (#595).

Real incident: test builds made with `@projectops apk build` **always failed**.
The build workflow had no `permissions:` block and followed the repo default,
and the default for new GitHub repos is `read`, so it was blocked the moment it posted a progress comment.

    RequestError [HttpError]: Resource not accessible by integration

The trigger workflow had the block, so **the trigger succeeded**. From outside it looked like
"the build runs but produces nothing", and finding the cause took a long time.

Not declaring is risky either way.
  default read  -> workflows that need write fail (the incident above)
  default write -> deploy workflows that only read get excessive permissions

So the rule is that **every workflow declares it explicitly**.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"

# Calls that write with GITHUB_TOKEN. If present, read permission alone always fails.
_WRITES_ISSUE = re.compile(
    r"createComment|updateComment|deleteComment|issues\.create\b|issues\.update\b"
    r"|addLabels|setLabels|removeLabel", re.I)


def workflows():
    return sorted(WF.rglob("*.y*ml"))


def _load(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _declared(doc: dict) -> bool:
    """Accepted whether declared at top level or per job."""
    if "permissions" in doc:
        return True
    jobs = doc.get("jobs") or {}
    return bool(jobs) and all("permissions" in (j or {}) for j in jobs.values())


@pytest.mark.parametrize("path", workflows(), ids=lambda p: p.name)
def test_every_workflow_declares_permissions(path):
    """Do not rely on the repo default — defaults differ per repo and change later."""
    assert _declared(_load(path)), (
        f"{path.relative_to(WF)} has no permissions declaration. "
        "Declare `contents: read` if it only reads, `issues: write` if it comments"
    )


# Triggers that start from issues. Comments posted here are **issue comments**, so issues: write is
# required. Comments on PRs use the same API (issues.createComment) but pull-requests: write
# is enough — not telling them apart would flag a healthy CI as failing.
_ISSUE_EVENTS = {"issues", "issue_comment", "repository_dispatch"}


def _scopes(doc: dict) -> dict:
    scopes = dict(doc.get("permissions") or {})
    for job in (doc.get("jobs") or {}).values():
        scopes.update((job or {}).get("permissions") or {})
    return scopes


def _comment_writer(path: Path):
    """(doc, scopes) if the workflow writes comments, else None."""
    text = path.read_text(encoding="utf-8")
    if not _WRITES_ISSUE.search(text):
        return None
    # Calls with a separate PAT are independent of GITHUB_TOKEN permissions
    if re.search(r"github-token:\s*\$\{\{\s*secrets\.(?!GITHUB_TOKEN)", text):
        return None
    doc = _load(path)
    return doc, _scopes(doc)


@pytest.mark.parametrize("path", workflows(), ids=lambda p: p.name)
def test_comment_writing_workflows_can_write(path):
    """Commenting without any write permission always dies at that step."""
    got = _comment_writer(path)
    if got is None:
        pytest.skip("this workflow does not comment with GITHUB_TOKEN")
    _, scopes = got
    assert "write" in (scopes.get("issues"), scopes.get("pull-requests")), (
        f"{path.relative_to(WF)} comments but has no write permission "
        f"(current: {scopes or 'none declared'})"
    )


@pytest.mark.parametrize("path", workflows(), ids=lambda p: p.name)
def test_issue_triggered_workflows_have_issues_write(path):
    """Comments from workflows that start from issues are issue comments.

    The real incident was exactly here — running via repository_dispatch it left progress on the issue
    without issues: write and stopped at the first comment.
    """
    got = _comment_writer(path)
    if got is None:
        pytest.skip("this workflow does not comment with GITHUB_TOKEN")
    doc, scopes = got
    events = doc.get(True) or doc.get("on") or {}      # PyYAML reads on: as True
    names = set(events) if isinstance(events, dict) else {events} if isinstance(events, str) else set(events or [])
    if not (names & _ISSUE_EVENTS):
        pytest.skip("does not start from issues")
    assert scopes.get("issues") == "write", (
        f"{path.relative_to(WF)} posts issue comments but has no issues: write "
        f"(current: {scopes or 'none declared'})"
    )
