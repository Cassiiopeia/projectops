"""Record 3 GitHub screen demo GIFs: issue guide comment, PR change summary, release automerge and tag (#976)

Install working-tree projectops into a temporary public repo (git-sandboxes/pops-qa-demo-gif-<lang>) > run for real >
capture with a logged-out browser > compose caption bar and elapsed timer > docs/images/feature-*.gif (ko is *.ko.gif)

Usage (from the repo root):
  uv run --with playwright --with pillow python docs/recording/github_demo/record_github.py --lang en
Needs: PAT (GITHUB_PAT or ~/.projectops/config) with org repo create/delete rights, node 20.12+, ffmpeg, Chromium
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
# Screen refresh interval while waiting (seconds), display time of waiting frames (seconds, fast-forward)
RELOAD_INTERVAL_SECONDS = 2.5
WAITING_FRAME_SECONDS = 0.45
WAIT_TIMEOUT_SECONDS = 600
# GitHub keeps connections open, so networkidle never comes > wait for render to settle after load (milliseconds)
PAGE_SETTLE_MILLISECONDS = 1500


class SceneRecorder:
    """One scene: elapsed timer from its start, capture > add frame"""

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
        """Refresh until the condition holds, recording waiting frames (real elapsed time stays in the timer)"""
        deadline = time.time() + WAIT_TIMEOUT_SECONDS
        while not is_done():
            if time.time() > deadline:
                raise SystemExit(f"[record github] step {step_number} timed out")
            time.sleep(RELOAD_INTERVAL_SECONDS)
            reload_fresh(self.page)
            self.capture(step_number, WAITING_FRAME_SECONDS)

    def wait_for_element(self, locator, step_number: int):
        """Refresh until a change confirmed by the API is drawn on screen too (logged-out page cache lag)"""
        self.wait_until(lambda: locator.count() > 0, step_number)


def reload_fresh(page):
    """Cache-busting refresh: timestamp in the URL > load > wait for render to settle"""
    base_url = page.url.split("?")[0].split("#")[0]
    page.goto(f"{base_url}?refresh={int(time.time() * 1000)}", wait_until="load")
    page.wait_for_timeout(PAGE_SETTLE_MILLISECONDS)


def snapshot_template(destination: Path):
    """Tracked + untracked (non-ignored) files > template snapshot (includes uncommitted changes)"""
    listed = subprocess.run(["git", "ls-files", "-z", "-co", "--exclude-standard"], cwd=REPO_ROOT,
                            check=True, capture_output=True).stdout.decode().split("\0")
    for relative_path in filter(None, listed):
        source = REPO_ROOT / relative_path
        if source.is_file():
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def create_sample_project(project_dir: Path):
    """Sample Spring project (main, 1 commit)"""
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
    """Code blocks in the comment body (branch name, then commit template)"""
    return [block.strip() for block in re.findall(r"```[^\n]*\n(.*?)```", comment_body, re.S)]


def record_issue_scene(page, repository, texts, composer, frame_dir) -> dict:
    """Open issue > wait for the issue helper run > highlight the branch name and commit template comment"""
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
    """Push 2 commits on the work branch > PR > wait for the change summary comment > highlight it"""
    DemoRepository.run_git(project_dir, "checkout", "-q", "-b", issue["branch_name"], "develop")
    for index, description in enumerate(texts["commit_descriptions"]):
        source_path = project_dir / f"src/main/java/com/example/NotificationSetting{index + 1}.java"
        source_path.write_text(f"package com.example;\n\npublic class NotificationSetting{index + 1} {{}}\n", encoding="utf-8")
        DemoRepository.run_git(project_dir, "add", "-A")
        # Commit template placeholder ({...}, wording differs per language) > real description
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
    # Comment box: shared by old (timeline-comment) and new (react-issue-comment) UI, else the body area
    summary_comment = heading.locator(
        "xpath=ancestor::*[contains(@class,'timeline-comment') or contains(@class,'react-issue-comment')"
        " or contains(@class,'markdown-body')][last()]")
    summary_comment.scroll_into_view_if_needed()
    # Nudge up a bit so the sticky header doesn't cover the top of the comment
    page.mouse.wheel(0, -110)
    page.wait_for_timeout(500)
    scene.capture(3, 4.0, summary_comment)
    return pull_request["number"]


def record_release_scene(page, repository, composer, frame_dir):
    """Merge the work PR > develop→main release PR > wait for automerge > highlight the tag"""
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
            # Label sync runs alongside on main push because the label file changed
            repository.install_projectops(project_dir, RECORDING_DIR / "run_local_projectops.mjs",
                                          work_dir / "template", args.lang)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                # Logged out, narrow screen (same framing as existing demos), shot at 2x then scaled down > sharp text
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
            # Clean up the temporary public repo (on success and failure)
            if not args.keep_repo:
                repository.delete()


if __name__ == "__main__":
    main()
