"""GitHub 화면 데모 GIF 3종 녹화: 이슈 안내 댓글, PR 변경 요약, 릴리스 자동 머지·태그 (#976)

임시 공개 레포(git-sandboxes/pops-qa-demo-gif-<언어>)에 작업 트리 projectops 설치 > 실제 실행 >
로그아웃 브라우저로 화면 캡처 > 설명 바·경과 타이머 합성 > docs/images/feature-*.gif (ko 는 *.ko.gif)

사용 (레포 루트에서):
  uv run --with playwright --with pillow python docs/recording/github_demo/record_github.py --lang en
필요: PAT(GITHUB_PAT 또는 ~/.projectops/config) 조직 레포 생성·삭제 권한, node 20.12+, ffmpeg, Chromium
  (uv run --with playwright playwright install chromium)
"""
import argparse
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from demo_repository import DemoRepository, load_github_pat
from demo_texts import DEMO_TEXTS
from gif_composer import FRAME_HEIGHT_PIXELS, FRAME_WIDTH_PIXELS, CapturedFrame, GifComposer

SANDBOX_OWNER = "git-sandboxes"
RECORDING_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = RECORDING_DIR.parent.parent
OUTPUT_DIR = REPO_ROOT / "docs" / "images"
# 대기 중 화면 새로고침 간격 (초), 대기 프레임 재생 시간 (초, 빨리 감기)
RELOAD_INTERVAL_SECONDS = 2.5
WAITING_FRAME_SECONDS = 0.45
WAIT_TIMEOUT_SECONDS = 600
# GitHub 은 상시 연결이 있어 networkidle 이 오지 않음 > load 후 렌더 안정 대기 (밀리초)
PAGE_SETTLE_MILLISECONDS = 1500


class SceneRecorder:
    """장면 하나: 시작 시각 기준 경과 타이머, 캡처 > 프레임 추가"""

    def __init__(self, page, composer: GifComposer, frame_dir: Path):
        self.page = page
        self.composer = composer
        self.frame_dir = frame_dir
        self.started_at = time.time()

    def capture(self, step_number: int, display_seconds: float, highlight_locator=None, is_timer_visible=True):
        highlight_box = None
        if highlight_locator is not None:
            box = highlight_locator.bounding_box()
            if box:
                highlight_box = (box["x"], box["y"], box["width"], box["height"])
        screenshot_path = self.frame_dir / f"{len(self.composer.frames):04d}.png"
        self.page.screenshot(path=str(screenshot_path))
        self.composer.add(CapturedFrame(screenshot_path, step_number, time.time() - self.started_at,
                                        display_seconds, highlight_box, is_timer_visible))

    def wait_until(self, is_done, step_number: int):
        """조건 충족까지 새로고침하며 대기 프레임 기록 (실제 경과는 타이머에 남음)"""
        deadline = time.time() + WAIT_TIMEOUT_SECONDS
        while not is_done():
            if time.time() > deadline:
                raise SystemExit(f"[record github] step {step_number} timed out")
            time.sleep(RELOAD_INTERVAL_SECONDS)
            reload_fresh(self.page)
            self.capture(step_number, WAITING_FRAME_SECONDS)

    def wait_for_element(self, locator, step_number: int):
        """API 로 확인된 변화가 화면에도 그려질 때까지 새로고침 (로그아웃 페이지 캐시 지연)"""
        self.wait_until(lambda: locator.count() > 0, step_number)


def reload_fresh(page):
    """캐시 우회 새로고침: 주소에 시각 값 > load > 렌더 안정 대기"""
    base_url = page.url.split("?")[0].split("#")[0]
    page.goto(f"{base_url}?refresh={int(time.time() * 1000)}", wait_until="load")
    page.wait_for_timeout(PAGE_SETTLE_MILLISECONDS)


def snapshot_template(destination: Path):
    """추적 + 미추적(무시 제외) 파일 > 템플릿 스냅샷 (커밋 전 변경 포함)"""
    listed = subprocess.run(["git", "ls-files", "-z", "-co", "--exclude-standard"], cwd=REPO_ROOT,
                            check=True, capture_output=True).stdout.decode().split("\0")
    for relative_path in filter(None, listed):
        source = REPO_ROOT / relative_path
        if source.is_file():
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def create_sample_project(project_dir: Path):
    """샘플 Spring 프로젝트 (main, 커밋 1개)"""
    (project_dir / "src/main/java/com/example").mkdir(parents=True)
    (project_dir / "build.gradle").write_text(
        "plugins {\n    id 'java'\n    id 'org.springframework.boot' version '3.3.4'\n}\n\n"
        "group = 'com.example'\nversion = '1.0.0'\n", encoding="utf-8")
    (project_dir / "src/main/java/com/example/App.java").write_text(
        "package com.example;\n\npublic class App {}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(project_dir)], check=True)
    DemoRepository.run_git(project_dir, "add", "-A")
    DemoRepository.run_git(project_dir, "commit", "-qm", "Initial commit")


def read_code_blocks(comment_body: str) -> list[str]:
    """댓글 본문 코드 블록 목록 (브랜치명, 커밋 템플릿 순)"""
    return [block.strip() for block in re.findall(r"```[^\n]*\n(.*?)```", comment_body, re.S)]


def record_issue_scene(page, repository, texts, composer, frame_dir) -> dict:
    """이슈 등록 > 이슈 헬퍼 실행 대기 > 브랜치명·커밋 템플릿 댓글 강조"""
    scene = SceneRecorder(page, composer, frame_dir)
    issue = repository.create_issue(texts["issue_title"], texts["issue_body"])
    page.goto(issue["html_url"], wait_until="load")
    page.wait_for_timeout(PAGE_SETTLE_MILLISECONDS)
    scene.capture(1, 2.0, is_timer_visible=False)
    marker = texts["issue_helper_marker"]
    scene.wait_until(lambda: repository.has_bot_comment(issue["number"], marker), 2)
    guide_comment = next(c for c in repository.list_comments(issue["number"]) if marker in c["body"])
    branch_name, commit_template = read_code_blocks(guide_comment["body"])[:2]
    branch_block = page.locator("pre").filter(has_text=branch_name).first
    commit_block = page.locator("pre").filter(has_text=commit_template.split(" : ")[0]).last
    scene.wait_for_element(page.locator("pre").filter(has_text=branch_name), 2)
    branch_block.scroll_into_view_if_needed()
    page.mouse.wheel(0, 150)
    page.wait_for_timeout(500)
    scene.capture(3, 3.0, branch_block)
    scene.capture(4, 3.5, commit_block)
    return {"number": issue["number"], "branch_name": branch_name, "commit_template": commit_template}


def record_pull_request_scene(page, repository, texts, composer, frame_dir, project_dir, issue) -> int:
    """작업 브랜치 커밋 2개 push > PR > 변경 요약 댓글 대기 > 댓글 강조"""
    DemoRepository.run_git(project_dir, "checkout", "-q", "-b", issue["branch_name"], "develop")
    for index, description in enumerate(texts["commit_descriptions"]):
        source_path = project_dir / f"src/main/java/com/example/NotificationSetting{index + 1}.java"
        source_path.write_text(f"package com.example;\n\npublic class NotificationSetting{index + 1} {{}}\n", encoding="utf-8")
        DemoRepository.run_git(project_dir, "add", "-A")
        # 커밋 템플릿의 자리표시자({...}, 언어마다 문구 다름) > 실제 설명
        commit_message = re.sub(r"\{[^}]*\}", description, issue["commit_template"], count=1)
        DemoRepository.run_git(project_dir, "commit", "-qm", commit_message)
    DemoRepository.run_git(project_dir, "push", "-q", "-u", "origin", issue["branch_name"])
    time.sleep(3)

    scene = SceneRecorder(page, composer, frame_dir)
    pull_request = repository.create_pull_request(issue["branch_name"], "develop", texts["pull_request_title"],
                                                  f"- #{issue['number']}")
    page.goto(pull_request["html_url"], wait_until="load")
    page.wait_for_timeout(PAGE_SETTLE_MILLISECONDS)
    scene.capture(1, 2.0, is_timer_visible=False)
    scene.wait_until(lambda: repository.has_bot_comment(pull_request["number"], "PROJECTOPS-AI-SUMMARY"), 2)
    scene.wait_for_element(page.get_by_text(texts["pull_request_summary_heading"]), 2)
    heading = page.get_by_text(texts["pull_request_summary_heading"]).last
    # 댓글 상자: 구 화면(timeline-comment) · 새 화면(react-issue-comment) 공통, 없으면 본문 영역
    summary_comment = heading.locator(
        "xpath=ancestor::*[contains(@class,'timeline-comment') or contains(@class,'react-issue-comment')"
        " or contains(@class,'markdown-body')][last()]")
    summary_comment.scroll_into_view_if_needed()
    # 고정 머리글이 댓글 윗부분을 가리지 않게 위로 조금
    page.mouse.wheel(0, -110)
    page.wait_for_timeout(500)
    scene.capture(3, 4.0, summary_comment)
    return pull_request["number"]


def record_release_scene(page, repository, composer, frame_dir):
    """작업 PR 머지 > develop→main 릴리스 PR > 자동 머지 대기 > 태그 강조"""
    scene = SceneRecorder(page, composer, frame_dir)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    release_pull_request = repository.create_pull_request("develop", "main", f"🚀 Deploy {today}", "")
    page.goto(release_pull_request["html_url"], wait_until="load")
    page.wait_for_timeout(PAGE_SETTLE_MILLISECONDS)
    scene.capture(1, 2.0, is_timer_visible=False)
    scene.wait_until(lambda: repository.get_pull_request(release_pull_request["number"])["merged"], 2)
    scene.wait_for_element(page.get_by_text("Merged", exact=True), 2)
    scene.capture(3, 2.5)
    deadline = time.time() + WAIT_TIMEOUT_SECONDS
    while not repository.list_tags():
        if time.time() > deadline:
            raise SystemExit("[record github] tag was not created")
        time.sleep(RELOAD_INTERVAL_SECONDS)
    page.goto(f"{repository.web_url}/tags", wait_until="load")
    page.wait_for_timeout(PAGE_SETTLE_MILLISECONDS)
    scene.wait_for_element(page.locator(".Box-row"), 3)
    scene.capture(4, 3.5, page.locator(".Box-row").first, is_timer_visible=False)


def main():
    parser = argparse.ArgumentParser(description="Record the GitHub demo GIFs")
    parser.add_argument("--lang", choices=sorted(DEMO_TEXTS), required=True)
    parser.add_argument("--keep-repo", action="store_true", help="keep the sandbox repository after recording")
    args = parser.parse_args()
    texts = DEMO_TEXTS[args.lang]
    file_suffix = "" if args.lang == "en" else f".{args.lang}"
    repository = DemoRepository(SANDBOX_OWNER, f"pops-qa-demo-gif-{args.lang}", load_github_pat())

    with tempfile.TemporaryDirectory(prefix="projectops-github-demo-") as work_root:
        work_dir = Path(work_root)
        snapshot_template(work_dir / "template")
        project_dir = work_dir / "demo-app"
        create_sample_project(project_dir)
        print(f"[record github] preparing {repository.full_name}")
        repository.recreate()
        try:
            # 라벨 동기화는 main push 때 라벨 파일 변경으로 함께 실행됨
            repository.install_projectops(project_dir, RECORDING_DIR / "run_local_projectops.mjs",
                                          work_dir / "template", args.lang)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                # 로그아웃 상태, 좁은 화면 (기존 데모와 같은 구도), 2배 해상도로 찍어 축소 > 글자 선명
                page = browser.new_page(viewport={"width": FRAME_WIDTH_PIXELS, "height": FRAME_HEIGHT_PIXELS},
                                        device_scale_factor=2, locale="en-US")
                scenes = {name: GifComposer(args.lang, texts["captions"][name], work_dir / name)
                          for name in ("issue", "pull_request", "release")}
                for composer in scenes.values():
                    (composer.work_dir / "frames").mkdir(parents=True)

                print("[record github] issue scene")
                issue = record_issue_scene(page, repository, texts, scenes["issue"], scenes["issue"].work_dir / "frames")
                print("[record github] pull request scene")
                pull_request_number = record_pull_request_scene(page, repository, texts, scenes["pull_request"],
                                                                scenes["pull_request"].work_dir / "frames", project_dir, issue)
                repository.merge_pull_request(pull_request_number)
                repository.wait_for_idle_workflows()
                print("[record github] release scene")
                record_release_scene(page, repository, scenes["release"], scenes["release"].work_dir / "frames")
                browser.close()

            output_names = {"issue": "feature-issue", "pull_request": "feature-pr-summary", "release": "feature-release"}
            for name, composer in scenes.items():
                output_path = OUTPUT_DIR / f"{output_names[name]}{file_suffix}.gif"
                composer.write_gif(output_path)
                print(f"[record github] wrote {output_path}")
        finally:
            # 임시 공개 레포 정리 (성공·실패 공통)
            if not args.keep_repo:
                repository.delete()


if __name__ == "__main__":
    main()
