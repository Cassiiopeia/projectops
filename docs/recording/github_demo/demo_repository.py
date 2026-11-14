"""Demo repo setup and actions: create, install projectops, issues, PRs, merges, wait for workflows (GitHub REST, standard library only)"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

API_ROOT = "https://api.github.com"
# Workflow wait limit (seconds)
WORKFLOW_WAIT_TIMEOUT_SECONDS = 600
POLL_INTERVAL_SECONDS = 3


def load_github_pat() -> str:
    """PAT: env var GITHUB_PAT > ~/.projectops/config/config.json github.global_pat"""
    if os.environ.get("GITHUB_PAT"):
        return os.environ["GITHUB_PAT"]
    config_path = Path.home() / ".projectops" / "config" / "config.json"
    if config_path.exists():
        pat = json.loads(config_path.read_text(encoding="utf-8")).get("github", {}).get("global_pat")
        if pat:
            return pat
    raise SystemExit("GITHUB_PAT not set and no global_pat in ~/.projectops/config/config.json")


class DemoRepository:
    """One temporary demo repo in the git-sandboxes org"""

    def __init__(self, owner: str, name: str, pat: str):
        self.owner = owner
        self.name = name
        self.pat = pat
        self.full_name = f"{owner}/{name}"
        self.web_url = f"https://github.com/{self.full_name}"

    # ── REST ──
    def request(self, method: str, path: str, body=None, is_missing_ok=False):
        url = path if path.startswith("http") else f"{API_ROOT}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"token {self.pat}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            if is_missing_ok and error.code == 404:
                return None
            raise SystemExit(f"[record github] {method} {path} failed {error.code}: {error.read()[:300]!r}")

    def repo_path(self, suffix: str = "") -> str:
        return f"/repos/{self.full_name}{suffix}"

    # ── Repo lifecycle ──
    def recreate(self):
        """Delete existing repo > create public repo (for logged-out screen captures) > Actions write permission"""
        if self.request("GET", self.repo_path(), is_missing_ok=True):
            self.request("DELETE", self.repo_path())
            time.sleep(3)
        self.request("POST", f"/orgs/{self.owner}/repos", {"name": self.name, "private": False, "auto_init": False})
        # Let release workflows commit and merge PRs: default token write + allow PR approval (ignored if org policy blocks it)
        try:
            self.request("PUT", self.repo_path("/actions/permissions/workflow"),
                         {"default_workflow_permissions": "write", "can_approve_pull_request_reviews": True})
        except SystemExit as error:
            print(f"[record github] workflow permission not changed: {error}")

    def delete(self):
        self.request("DELETE", self.repo_path(), is_missing_ok=True)

    # ── git ──
    def push_url(self) -> str:
        return f"https://x-access-token:{self.pat}@github.com/{self.full_name}.git"

    @staticmethod
    def run_git(project_dir: Path, *args: str):
        subprocess.run(["git", "-C", str(project_dir), "-c", "user.name=projectops-demo",
                        "-c", "user.email=demo@example.com", *args], check=True, capture_output=True)

    def install_projectops(self, project_dir: Path, runner: Path, template_dir: Path, language: str):
        """Sample Spring project > non-interactive install with the working-tree CLI > push main and develop"""
        subprocess.run(["node", str(runner), str(template_dir), "--mode", "full", "--type", "spring",
                        "--deploy", "none", "--language", language, "--force"],
                       cwd=project_dir, check=True, capture_output=True,
                       env={**os.environ, "PROJECTOPS_LANG": language})
        self.run_git(project_dir, "add", "-A")
        self.run_git(project_dir, "commit", "-qm", "Install projectops")
        self.run_git(project_dir, "remote", "add", "origin", self.push_url())
        self.run_git(project_dir, "push", "-q", "-u", "origin", "main")
        self.wait_for_idle_workflows()
        # Create develop only after pulling the version commit from the direct main push
        self.run_git(project_dir, "pull", "-q", "--rebase", "origin", "main")
        self.run_git(project_dir, "checkout", "-q", "-b", "develop")
        self.run_git(project_dir, "push", "-q", "-u", "origin", "develop")
        self.wait_for_idle_workflows()

    # ── Workflows ──
    def wait_for_idle_workflows(self, timeout_seconds: int = WORKFLOW_WAIT_TIMEOUT_SECONDS):
        """Wait until no run is in progress or queued (waits before the first check, since runs register late after a push)"""
        time.sleep(8)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            runs = self.request("GET", self.repo_path("/actions/runs?per_page=30"))["workflow_runs"]
            if not any(self.is_run_active(run) for run in runs):
                return
            time.sleep(POLL_INTERVAL_SECONDS)
        raise SystemExit("[record github] workflows did not finish in time")

    def is_run_active(self, run: dict) -> bool:
        """Whether a run is in progress (if run status updates late, treat it as done once all jobs finished)"""
        if run["status"] not in ("queued", "in_progress", "waiting", "pending", "requested"):
            return False
        jobs = self.request("GET", run["jobs_url"])["jobs"]
        return not jobs or any(job["status"] != "completed" for job in jobs)

    # ── Issues and PRs ──
    def create_issue(self, title: str, body: str) -> dict:
        return self.request("POST", self.repo_path("/issues"), {"title": title, "body": body})

    def list_comments(self, number: int) -> list:
        return self.request("GET", self.repo_path(f"/issues/{number}/comments?per_page=50"))

    def has_bot_comment(self, number: int, marker: str) -> bool:
        return any(marker in (comment.get("body") or "") for comment in self.list_comments(number))

    def create_pull_request(self, head: str, base: str, title: str, body: str) -> dict:
        return self.request("POST", self.repo_path("/pulls"), {"head": head, "base": base, "title": title, "body": body})

    def get_pull_request(self, number: int) -> dict:
        return self.request("GET", self.repo_path(f"/pulls/{number}"))

    def merge_pull_request(self, number: int):
        self.request("PUT", self.repo_path(f"/pulls/{number}/merge"), {"merge_method": "merge"})

    def list_tags(self) -> list:
        return self.request("GET", self.repo_path("/tags"))
