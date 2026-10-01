"""배포 워크플로 사전 점검과 첫 설치 직후 실패 방지 (#666 #667 #668 #669 #696).

신규 설치 직후에는 Secret, Dockerfile, lock 파일이 없는 것이 정상이다. 그 상태에서도
"무엇이 없는지"가 첫 줄에 나오거나, 선택 기능은 조용히 건너뛰어야 한다.
실제 GitHub Actions 동작은 로컬에서 증명할 수 없어 여기서는 구조(조건, 순서, 정본-복사본 일치)만 본다.
"""
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"
PT = WF / "project-types"


def _jobs(p: Path) -> dict:
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("jobs", {})


def _step_names(job: dict) -> list:
    return [st.get("name", "") for st in job.get("steps", [])]


# ── #696 setup-java ─────────────────────────────────────────────
def test_setup_java_v3_not_used():
    bad = [str(p.relative_to(ROOT)) for p in WF.rglob("*.y*ml")
           if "actions/setup-java@v3" in p.read_text(encoding="utf-8")]
    assert not bad, f"setup-java@v3 잔존: {bad}"


# ── #666 사전 점검 ──────────────────────────────────────────────
# (파일, job, 점검 step 이름 일부, 반드시 언급해야 하는 항목)
PREFLIGHT = [
    (PT / "spring/server-deploy/PROJECT-SPRING-SIMPLE-CICD.yaml", "build", "사전 점검",
     ["gradlew", "DOCKERFILE_PATH", "DOCKERHUB_TOKEN", "SERVER_HOST", "SSH_KEY", "SERVER_PASSWORD"]),
    (PT / "python/server-deploy/PROJECT-PYTHON-SIMPLE-CICD.yaml", "build", "사전 점검",
     ["Dockerfile", "DOCKERHUB_TOKEN", "SERVER_HOST", "SSH_KEY", "SERVER_PASSWORD"]),
    (PT / "react/PROJECT-REACT-CICD.yaml", "build", "사전 점검",
     ["Dockerfile", "DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN", "SERVER_HOST", "SERVER_USER", "SERVER_PASSWORD"]),
    (PT / "python/PROJECT-PYTHON-CI.yaml", "build-check", "사전 점검", ["Dockerfile"]),
    (PT / "flutter/PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml", "build-android", "사전 점검",
     ["SERVER_HOST", "SERVER_USER", "SERVER_PASSWORD"]),
    (PT / "flutter/PROJECT-FLUTTER-ANDROID-FIREBASE-CICD.yaml", "prepare-build", "사전 점검",
     ["FIREBASE_SERVICE_ACCOUNT_JSON_BASE64"]),
    (PT / "flutter/PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD.yaml", "prepare-build", "사전 점검",
     ["GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64"]),
    (PT / "flutter/PROJECT-FLUTTER-IOS-TESTFLIGHT.yaml", "prepare-build", "사전 점검",
     ["APPLE_CERTIFICATE_BASE64", "APPLE_PROVISIONING_PROFILE_BASE64", "APP_STORE_CONNECT_API_KEY_BASE64"]),
]


@pytest.mark.parametrize("path,job,key,items", PREFLIGHT, ids=lambda v: getattr(v, "name", None) or None)
def test_preflight_step_is_first_expensive_step(path, job, key, items):
    steps = _jobs(path)[job]["steps"]
    idx = next((i for i, st in enumerate(steps) if key in st.get("name", "")), None)
    assert idx is not None, f"{path.name}: 사전 점검 step 없음"
    # 체크아웃 직후까지만 허용 (빌드·로그인·설치 같은 비싼 step 보다 앞)
    for st in steps[:idx]:
        assert "uses" in st and "checkout" in st["uses"], \
            f"{path.name}: 사전 점검 앞에 체크아웃 외 step 이 있다: {st.get('name')}"
    body = yaml.dump(steps[idx], allow_unicode=True)
    for it in items:
        assert it in body, f"{path.name}: 점검 항목 {it} 누락"
    # 실패는 ::error:: 로 알리고 비정상 종료해야 한다
    assert "::error" in body and "exit 1" in body


def test_selfhosted_preflight_only_on_main():
    # 배포 job 이 main 에서만 도므로, 다른 브랜치 수동 실행(빌드만)을 막으면 안 된다
    steps = _jobs(PT / "flutter/PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml")["build-android"]["steps"]
    st = next(s for s in steps if "사전 점검" in s.get("name", ""))
    assert "refs/heads/main" in st.get("if", "")


# ── #667 Projects Sync 미설정 ───────────────────────────────────
def test_projects_sync_skips_when_unconfigured():
    p = WF / "PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml"
    steps = _jobs(p)["sync-label-to-status"]["steps"]
    assert steps[0].get("id") == "config", "설정 확인이 첫 step 이어야 한다"
    env = steps[0]["env"]
    assert "_GITHUB_PAT_TOKEN" in env["HAS_PAT"] and "PROJECT_URL" in env["HAS_PROJECT_URL"]
    # 이후 step 은 전부 설정 확인 결과로 가드돼야 한다 (PAT 없는 github-script 가 죽는 것이 원인이었다)
    for st in steps[1:]:
        assert "steps.config.outputs.enabled == 'true'" in str(st.get("if", "")), st.get("name")
    # 미설정은 실패가 아니라 안내 후 성공
    assert "exit 1" not in steps[0]["run"]


# ── #668 라벨 동기화 트리거 ─────────────────────────────────────
def test_label_sync_runs_on_main_push_without_paths_filter():
    """paths 필터는 새 레포의 첫 push 에서 평가되지 않아 라벨이 안 만들어졌다(#668 실측) — 브랜치 조건만 둔다."""
    for base in (WF, WF / "project-types" / "common"):
        d = yaml.safe_load((base / "PROJECT-COMMON-SYNC-ISSUE-LABELS.yaml").read_text(encoding="utf-8"))
        on = d.get("on") or d.get(True)  # PyYAML 은 on 을 True 로 읽는다
        assert "paths" not in on["push"], base
        assert on["push"]["branches"] == ["main"], base
        assert "workflow_dispatch" in on
        # 동시 실행 충돌 방지와 사용자 라벨 보존은 유지돼야 한다
        assert d["concurrency"]["cancel-in-progress"] is False
        text = (base / "PROJECT-COMMON-SYNC-ISSUE-LABELS.yaml").read_text(encoding="utf-8")
        assert "skip-delete: true" in text


def test_setup_guide_and_summary_mention_label_sync():
    guide = (ROOT / "PROJECTOPS-SETUP-GUIDE.md").read_text(encoding="utf-8")
    assert "PROJECT-SYNC-GITHUB-LABELS" in guide and "Run workflow" in guide
    summary = (ROOT / "src/ui/summary.js").read_text(encoding="utf-8")
    assert "PROJECT-SYNC-GITHUB-LABELS" in summary


# ── #669 React 패키지 매니저 ────────────────────────────────────
@pytest.mark.parametrize("name", ["PROJECT-REACT-CI.yaml", "PROJECT-REACT-CICD.yaml"])
def test_react_detects_package_manager(name):
    p = PT / "react" / name
    text = p.read_text(encoding="utf-8")
    steps = _jobs(p)["build"]["steps"]
    names = _step_names(_jobs(p)["build"])
    assert names.index("패키지 매니저 감지") < names.index("Node.js 설정")
    node = next(s for s in steps if s.get("name") == "Node.js 설정")
    # 하드코딩된 cache: npm 이 lock 없는 레포에서 첫 step 부터 죽이던 원인
    assert node["with"]["cache"] == "${{ steps.pm.outputs.cache }}"
    for cmd in ("npm ci", "pnpm install --frozen-lockfile", "yarn install", "npm install"):
        assert cmd in text
    # 기존 npm(package-lock.json) 경로가 최우선이어야 기존 동작이 안 바뀐다
    detect = next(s for s in steps if s.get("name") == "패키지 매니저 감지")["run"]
    assert detect.index("package-lock.json") < detect.index("pnpm-lock.yaml") < detect.index("yarn.lock")


def test_react_detect_script_runs(tmp_path):
    """감지 스크립트를 실제로 돌려 lock 종류별 결과를 본다."""
    steps = _jobs(PT / "react/PROJECT-REACT-CI.yaml")["build"]["steps"]
    script = next(s for s in steps if s.get("name") == "패키지 매니저 감지")["run"]
    cases = {
        "package-lock.json": ("npm", "npm"),
        "pnpm-lock.yaml": ("pnpm", "pnpm"),
        "yarn.lock": ("yarn", "yarn"),
        None: ("none", ""),
    }
    for lock, (mgr, cache) in cases.items():
        d = tmp_path / (lock or "nolock")
        d.mkdir()
        if lock:
            (d / lock).write_text("")
        out = d / "out.txt"
        r = subprocess.run(["bash", "-e", "-c", script], cwd=d, capture_output=True, text=True,
                           env={"GITHUB_OUTPUT": str(out), "PATH": "/usr/bin:/bin"})
        assert r.returncode == 0, r.stderr
        got = dict(l.split("=", 1) for l in out.read_text().splitlines())
        assert got == {"manager": mgr, "cache": cache}, (lock, got)


# ── 사전 점검 스크립트 실행 ─────────────────────────────────────
def _run_step(step: dict, cwd: Path, env: dict):
    return subprocess.run(["bash", "-e", "-c", step["run"]], cwd=cwd, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", **env})


def test_spring_preflight_reports_missing_and_passes_when_complete(tmp_path):
    steps = _jobs(PT / "spring/server-deploy/PROJECT-SPRING-SIMPLE-CICD.yaml")["build"]["steps"]
    st = next(s for s in steps if "사전 점검" in s.get("name", ""))
    r = _run_step(st, tmp_path, {"DOCKERFILE_PATH": "./Dockerfile", "SSH_AUTH_METHOD": "password"})
    assert r.returncode == 1
    for needle in ("gradlew", "Dockerfile", "DOCKERHUB_USERNAME", "SERVER_PASSWORD"):
        assert needle in r.stdout
    # 전부 갖추면 통과
    (tmp_path / "gradlew").write_text("")
    (tmp_path / "Dockerfile").write_text("")
    env = {"DOCKERFILE_PATH": "./Dockerfile", "SSH_AUTH_METHOD": "password", "DOCKERHUB_USERNAME": "u",
           "DOCKERHUB_TOKEN": "t", "SERVER_HOST": "h", "SERVER_USER": "u", "SERVER_PASSWORD": "p"}
    assert _run_step(st, tmp_path, env).returncode == 0
    # key 방식이면 SERVER_PASSWORD 대신 SSH_KEY 를 요구한다
    env2 = {**env, "SSH_AUTH_METHOD": "key", "SERVER_PASSWORD": ""}
    r2 = _run_step(st, tmp_path, env2)
    assert r2.returncode == 1 and "SSH_KEY" in r2.stdout
    assert _run_step(st, tmp_path, {**env2, "SSH_KEY": "k"}).returncode == 0


def test_react_cicd_preflight_reports_missing_and_passes_when_complete(tmp_path):
    steps = _jobs(PT / "react/PROJECT-REACT-CICD.yaml")["build"]["steps"]
    st = next(s for s in steps if "사전 점검" in s.get("name", ""))
    r = _run_step(st, tmp_path, {})
    assert r.returncode == 1
    for needle in ("Dockerfile", "DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN", "SERVER_HOST", "SERVER_USER", "SERVER_PASSWORD"):
        assert needle in r.stdout
    env = {"DOCKERHUB_USERNAME": "u", "DOCKERHUB_TOKEN": "t", "SERVER_HOST": "h",
           "SERVER_USER": "u", "SERVER_PASSWORD": "p"}
    # Secret 만 있고 Dockerfile 이 없으면 Dockerfile 만 지적한다
    r2 = _run_step(st, tmp_path, env)
    assert r2.returncode == 1 and "Dockerfile" in r2.stdout and "Secret" not in r2.stdout
    (tmp_path / "Dockerfile").write_text("")
    assert _run_step(st, tmp_path, env).returncode == 0


# ── 정본(common/)과 루트 복사본 동일 ────────────────────────────
@pytest.mark.parametrize("name", ["PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml", "PROJECT-COMMON-SYNC-ISSUE-LABELS.yaml"])
def test_common_copy_identical(name):
    assert (WF / name).read_text(encoding="utf-8") == (PT / "common" / name).read_text(encoding="utf-8")
