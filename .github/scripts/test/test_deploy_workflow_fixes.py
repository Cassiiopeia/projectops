"""README 없는 프로젝트의 버전 워크플로(#726)와 운영 배포 컨테이너 재시작 정책(#727) 회귀 방지."""
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"
PT = WF / "project-types"

PRODUCTION = [
    "spring/server-deploy/PROJECT-SPRING-SIMPLE-CICD.yaml",
    "python/server-deploy/PROJECT-PYTHON-SIMPLE-CICD.yaml",
    "react/PROJECT-REACT-CICD.yaml",
    "spring/server-deploy/PROJECT-SPRING-NONSTOP-TRAEFIK-CICD.yaml",
    "spring/server-deploy/PROJECT-SPRING-NONSTOP-NGINX-CICD.yaml",
]
PREVIEW = ["spring/server-deploy/PROJECT-SPRING-PR-PREVIEW.yaml", "python/server-deploy/PROJECT-PYTHON-PR-PREVIEW.yaml"]


def _readme_step_script(base):
    d = yaml.safe_load((base / "PROJECT-COMMON-README-VERSION-UPDATE.yaml").read_text(encoding="utf-8"))
    steps = [s for j in d["jobs"].values() for s in j["steps"] if "README.md 파일 버전 정보 업데이트" in s.get("name", "")]
    assert len(steps) == 1
    return steps[0]["run"]


@pytest.mark.parametrize("base", [WF, PT / "common"], ids=["root", "common"])
def test_readme_없으면_안내만_남기고_성공으로_건너뛴다(base, tmp_path):
    script = _readme_step_script(base)
    # 가드(README 존재 확인)가 있는 앞부분만 실행한다: ${{ }} 식은 빈 값으로 치환
    head = script.split("# 다양한 버전 표기 패턴")[0]
    head = head.replace("${{ steps.version_info.outputs.latest_version }}", "1.0.0") \
               .replace("${{ steps.version_info.outputs.release_date }}", "2026-10-01") \
               .replace("${{ env.SHOW_DATE }}", "false")
    r = subprocess.run(["bash", "-c", head + "\necho REACHED_END"], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "::notice::README.md" in r.stdout
    assert "REACHED_END" not in r.stdout  # 가드에서 exit 0 으로 끝나야 한다


@pytest.mark.parametrize("base", [WF, PT / "common"], ids=["root", "common"])
def test_readme_없어도_커밋_step_이_pathspec_오류로_죽지_않는다(base, tmp_path):
    """가드 step 이 통과해도 다음 step 의 git add README.md 가 128 로 죽던 실제 사고(#726)."""
    d = yaml.safe_load((base / "PROJECT-COMMON-README-VERSION-UPDATE.yaml").read_text(encoding="utf-8"))
    run = [s["run"] for j in d["jobs"].values() for s in j["steps"] if s.get("name") == "변경사항 커밋 및 푸시"][0]
    head = run.split("if git diff --staged --quiet")[0]
    head = head.replace("${{ github.event.repository.default_branch || 'main' }}", "main")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    r = subprocess.run(["bash", "-e", "-c", head + "\necho OK"], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


@pytest.mark.parametrize("rel", PRODUCTION)
def test_운영_배포_컨테이너는_재시작_정책을_가진다(rel):
    t = (PT / rel).read_text(encoding="utf-8")
    block = t[t.index("docker run -d"):][:700]
    assert "--restart unless-stopped" in block, rel


@pytest.mark.parametrize("rel", PREVIEW)
def test_pr_프리뷰_컨테이너는_재시작_정책을_넣지_않는다(rel):
    t = (PT / rel).read_text(encoding="utf-8")
    assert "--restart" not in t, rel


@pytest.mark.parametrize("rel", PRODUCTION)
def test_docker_run_이어쓰기_명령_안에_주석_줄이_없다(rel):
    """역슬래시로 이어지는 명령 중간의 # 줄은 명령을 끊어 'docker run requires at least 1 argument' 가 된다.
    실제 서버 배포에서 터진 사고라 텍스트가 아니라 구조로 막는다 (#727)."""
    lines = (PT / rel).read_text(encoding="utf-8").split("\n")
    for i, l in enumerate(lines):
        if "docker run -d" not in l:
            continue
        k = i
        while lines[k].rstrip().endswith("\\"):
            k += 1
            assert not lines[k].strip().startswith("#"), f"{rel}:{k + 1} 이어쓰기 명령 중간에 주석 줄"
        break
