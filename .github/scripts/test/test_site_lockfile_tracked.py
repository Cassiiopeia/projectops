# .github/scripts/test/test_site_lockfile_tracked.py
"""문서 사이트의 package-lock.json 이 git 에 추적되는지 검증 (#755).

실사고: 루트 .gitignore 가 package-lock.json 을 무시해 `git add site` 가 락 파일을 조용히 빼먹었고,
CI 의 `npm ci` 가 "package-lock.json 이 없다"며 Pages 배포가 실패했다. 로컬에는 파일이 있어
로컬 빌드로는 잡히지 않는다.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _tracked(path):
    out = subprocess.run(["git", "ls-files", path], cwd=ROOT, capture_output=True, text=True).stdout
    return bool(out.strip())


def test_site_lockfile_is_tracked():
    assert _tracked("site/package-lock.json"), (
        "site/package-lock.json 이 추적되지 않는다. 루트 .gitignore 의 package-lock.json 규칙에 "
        "`!site/package-lock.json` 예외가 있는지 확인하라 (CI 의 npm ci 가 실패한다)."
    )


def test_deploy_workflow_uses_npm_ci_with_that_lockfile():
    wf = (ROOT / ".github/workflows/PROJECT-TEMPLATE-DOCS-DEPLOY.yaml").read_text(encoding="utf-8")
    assert "npm ci" in wf  # npm ci 를 쓰는 한 락 파일이 반드시 필요하다
