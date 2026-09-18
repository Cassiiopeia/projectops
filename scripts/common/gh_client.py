"""GitHub REST API 클라이언트 — urllib 표준 라이브러리만 사용."""

from __future__ import annotations

import base64
import datetime
import json
import mimetypes
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


_API_BASE = "https://api.github.com"


class GitHubAPIError(Exception):
    """GitHub API 요청 중 발생하는 에러."""
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"GitHub API {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class PyNaClMissingError(Exception):
    """Actions Secret 암호화에 필요한 PyNaCl을 사용할 수 없을 때 발생."""
    code = "pynacl_missing"


class _StripAuthRedirect(urllib.request.HTTPRedirectHandler):
    """redirect 시 Authorization 헤더를 제거한다.

    GitHub job logs 등 일부 엔드포인트는 Azure Blob(SAS URL)로 302 redirect되는데,
    urllib 기본 동작은 Authorization 헤더를 redirect 대상까지 전달한다.
    Azure는 이를 거부하고 403 AuthenticationFailed를 반환하므로 헤더를 제거해야 한다.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
        return new


_opener = urllib.request.build_opener(_StripAuthRedirect)


def _request(method: str, url: str, data: dict | None, pat: str, raw: bool = False) -> Any:
    """GitHub API 요청을 보내고 응답을 반환한다.

    raw=False: 응답 본문을 JSON으로 파싱해 반환.
    raw=True: 디코딩한 텍스트(str)를 그대로 반환 (로그 등 비 JSON 응답용).
    """
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "projectops",
        },
    )
    try:
        with _opener.open(req) as resp:
            content = resp.read()
            if not content:
                return {} if not raw else ""
            if raw:
                return content.decode("utf-8", "replace")
            return json.loads(content.decode())
    except urllib.error.HTTPError as e:
        body_bytes = e.fp.read() if e.fp else b""
        try:
            msg = json.loads(body_bytes).get("message", str(e))
        except Exception:
            msg = body_bytes.decode("utf-8", "replace")[:200] or str(e)
        raise GitHubAPIError(e.code, msg) from e


def list_labels(owner: str, repo: str, pat: str) -> list[str]:
    """레포의 라벨 이름 목록을 반환한다."""
    items = _request("GET", f"{_API_BASE}/repos/{owner}/{repo}/labels?per_page=100", None, pat)
    return [item["name"] for item in items]


def add_issue_labels(owner: str, repo: str, issue_number: int, labels: list[str], pat: str) -> list[str]:
    """이슈/PR(GitHub API에선 둘 다 issue)에 라벨을 추가한다 (덮어쓰기 아님).

    PR도 GitHub API에서는 issue로 다뤄지므로 `/issues/{n}/labels`로 호출 가능.
    레포에 존재하지 않는 라벨은 사전 필터링해 422를 방지한다.
    반환: 이슈/PR에 현재 붙어 있는 모든 라벨 이름 리스트.
    """
    if not labels:
        return []
    existing = set(list_labels(owner, repo, pat))
    filtered = [l for l in labels if l in existing]
    if not filtered:
        return []
    items = _request(
        "POST",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/labels",
        {"labels": filtered},
        pat,
    )
    return [item["name"] for item in items]


def remove_issue_label(
    owner: str, repo: str, issue_number: int, name: str, pat: str,
) -> dict:
    """이슈에서 라벨 하나만 제거한다 (나머지 라벨은 유지).

    라벨명은 URL 경로에 들어가므로 반드시 인코딩한다 (한글 라벨 `작업중` 등).
    이슈에 그 라벨이 없으면 404가 나므로 호출자가 멱등 처리한다.
    반환: 제거 후 이슈에 남은 라벨 이름 리스트.
    """
    enc = urllib.parse.quote(name, safe="")
    items = _request(
        "DELETE",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/labels/{enc}",
        None,
        pat,
    )
    return {"labels": [item["name"] for item in items]}


def set_issue_labels(
    owner: str, repo: str, issue_number: int, labels: list[str], pat: str,
) -> dict:
    """이슈의 라벨을 통째로 교체한다 (기존 라벨 전부 제거 후 새 배열 적용).

    빈 배열이면 모든 라벨을 제거한다. 존재하지 않는 라벨은 사전 필터링해 422를 방지한다.
    반환: 교체 후 이슈에 붙은 라벨 이름 리스트.
    """
    if labels:
        existing = set(list_labels(owner, repo, pat))
        labels = [l for l in labels if l in existing]
    items = _request(
        "PUT",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/labels",
        {"labels": labels},
        pat,
    )
    return {"labels": [item["name"] for item in items]}


def create_issue(
    owner: str, repo: str, title: str, body: str,
    labels: list[str], pat: str, assignees: list[str] | None = None,
) -> dict:
    """이슈를 생성하고 {number, url, title}을 반환한다."""
    # 존재하지 않는 라벨은 422를 유발하므로 사전에 필터링
    if labels:
        existing = list_labels(owner, repo, pat)
        labels = [l for l in labels if l in existing]
    payload: dict = {"title": title, "body": body, "labels": labels}
    if assignees:
        payload["assignees"] = assignees
    data = _request("POST", f"{_API_BASE}/repos/{owner}/{repo}/issues", payload, pat)
    # 실제 반영된 담당자를 함께 반환한다. 유효하지 않은 담당자(레포 협업자 아님 등)는
    # GitHub이 조용히 누락시키므로, 호출자가 요청 대비 반영 결과를 비교해 경고할 수 있게 한다.
    return {
        "number": data["number"],
        "url": data["html_url"],
        "title": data["title"],
        "assignees": [u["login"] for u in data.get("assignees", [])],
    }


def update_issue(
    owner: str, repo: str, issue_number: int, pat: str,
    title: str | None = None, body: str | None = None,
    state: str | None = None, labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> dict:
    """이슈를 수정하고 {number, url, title}을 반환한다."""
    payload: dict = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state is not None:
        payload["state"] = state
    if labels is not None:
        payload["labels"] = labels
    if assignees is not None:
        payload["assignees"] = assignees
    data = _request("PATCH", f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}", payload, pat)
    return {"number": data["number"], "url": data["html_url"], "title": data["title"]}


def add_assignees(
    owner: str, repo: str, issue_number: int, assignees: list[str], pat: str,
) -> dict:
    """이슈에 담당자를 추가한다 (기존 담당자 유지). 최대 10명.

    권한 없는/존재하지 않는 유저는 GitHub이 조용히 누락시키므로,
    응답의 실제 담당자 목록을 반환해 호출자가 요청 대비 확인할 수 있게 한다.
    """
    data = _request(
        "POST",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/assignees",
        {"assignees": assignees},
        pat,
    )
    return {
        "number": data["number"],
        "url": data["html_url"],
        "assignees": [u["login"] for u in data.get("assignees", [])],
    }


def remove_assignees(
    owner: str, repo: str, issue_number: int, assignees: list[str], pat: str,
) -> dict:
    """이슈에서 지정한 담당자만 제거한다 (나머지 담당자 유지).

    이 DELETE는 body가 필요하다. 지정 목록에 없는 담당자는 그대로 남는다.
    """
    data = _request(
        "DELETE",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/assignees",
        {"assignees": assignees},
        pat,
    )
    return {
        "number": data["number"],
        "url": data["html_url"],
        "assignees": [u["login"] for u in data.get("assignees", [])],
    }


def add_comment(
    owner: str, repo: str, issue_number: int, body: str, pat: str,
) -> dict:
    """이슈/PR에 댓글을 추가하고 {id, url}을 반환한다.

    PR도 GitHub API에서는 issue로 다뤄지므로 PR 번호로도 호출 가능하다.
    """
    data = _request(
        "POST",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments",
        {"body": body},
        pat,
    )
    return {"id": data["id"], "url": data["html_url"]}


def update_comment(
    owner: str, repo: str, comment_id: int, body: str, pat: str,
) -> dict:
    """이슈/PR 댓글 하나의 본문을 수정하고 {id, url}을 반환한다.

    엔드포인트가 issue_number 없이 comment_id만 쓴다 (issue·PR 공용).
    """
    data = _request(
        "PATCH",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/comments/{comment_id}",
        {"body": body},
        pat,
    )
    return {"id": data["id"], "url": data["html_url"]}


def delete_comment(
    owner: str, repo: str, comment_id: int, pat: str,
) -> dict:
    """이슈/PR 댓글 하나를 삭제한다. 204(빈 본문) 응답이므로 파싱하지 않는다."""
    _request(
        "DELETE",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/comments/{comment_id}",
        None,
        pat,
    )
    return {"comment_id": comment_id, "status": "deleted"}


def get_issue(owner: str, repo: str, issue_number: int, pat: str) -> dict:
    """이슈를 조회하고 agent 판단에 필요한 요약 필드를 반환한다."""
    data = _request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}",
        None,
        pat,
    )
    return {
        "number": data["number"],
        "title": data["title"],
        "url": data["html_url"],
        "state": data["state"],
        "body": data.get("body", ""),
        "labels": [item["name"] for item in data.get("labels", [])],
        "assignees": [item["login"] for item in data.get("assignees", [])],
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "comments_count": data.get("comments", 0),
    }


def get_issue_comments(owner: str, repo: str, issue_number: int, pat: str) -> list[dict]:
    """이슈 댓글 목록을 agent가 바로 읽기 쉬운 형태로 반환한다."""
    items = _request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments?per_page=100",
        None,
        pat,
    )
    return [
        {
            "author": (item.get("user") or {}).get("login"),
            "body": item.get("body", ""),
            "created_at": item.get("created_at"),
        }
        for item in items
    ]


def list_issues(
    owner: str, repo: str, pat: str, state: str = "open",
) -> list[dict]:
    """이슈 목록을 조회한다."""
    items = _request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/issues?state={state}&per_page=50",
        None,
        pat,
    )
    return [
        {"number": i["number"], "title": i["title"], "url": i["html_url"], "state": i["state"]}
        for i in items
    ]


# --- Repository exploration ---

def get_user_type(owner: str, pat: str) -> str:
    """GitHub owner 타입을 user/org 중 하나로 반환한다."""
    data = _request("GET", f"{_API_BASE}/users/{owner}", None, pat)
    return "org" if data.get("type") == "Organization" else "user"


def list_repos(owner: str, repo_type: str, pat: str) -> list[dict]:
    """사용자 또는 조직의 레포 목록을 반환한다."""
    endpoint = "orgs" if repo_type == "org" else "users"
    items = _request("GET", f"{_API_BASE}/{endpoint}/{owner}/repos?per_page=100&sort=updated", None, pat)
    return [
        {
            "name": item["name"],
            "desc": item.get("description"),
            "lang": item.get("language"),
            "stars": item.get("stargazers_count", 0),
            "updated": item.get("updated_at"),
            "fork": item.get("fork", False),
            "private": item.get("private", False),
            "url": item.get("html_url"),
            "topics": item.get("topics", []),
        }
        for item in items
    ]


def get_repo_detail(owner: str, repo: str, pat: str) -> dict:
    """레포 상세 정보를 반환한다."""
    data = _request("GET", f"{_API_BASE}/repos/{owner}/{repo}", None, pat)
    return {
        "name": data["name"],
        "desc": data.get("description"),
        "lang": data.get("language"),
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "default_branch": data.get("default_branch"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "topics": data.get("topics", []),
        "url": data.get("html_url"),
    }


def get_readme(owner: str, repo: str, pat: str) -> dict:
    """README 내용을 base64 디코딩해 반환한다. 없으면 content=None."""
    try:
        data = _request("GET", f"{_API_BASE}/repos/{owner}/{repo}/readme", None, pat)
    except GitHubAPIError as e:
        if e.status_code == 404:
            return {"content": None}
        raise
    content = data.get("content")
    if not content:
        return {"content": None}
    if data.get("encoding") == "base64":
        decoded = base64.b64decode(content).decode("utf-8", "replace")
        return {"content": decoded}
    return {"content": content}


def get_languages(owner: str, repo: str, pat: str) -> list[dict]:
    """언어별 비율을 내림차순으로 반환한다."""
    data = _request("GET", f"{_API_BASE}/repos/{owner}/{repo}/languages", None, pat)
    total = sum(data.values())
    if total <= 0:
        return []
    return [
        {"lang": lang, "percent": round((size / total) * 100, 1)}
        for lang, size in sorted(data.items(), key=lambda item: item[1], reverse=True)
    ]


def list_commits(owner: str, repo: str, pat: str, limit: int = 10) -> list[dict]:
    """최근 커밋 목록을 반환한다."""
    limit = max(1, min(limit, 100))
    items = _request("GET", f"{_API_BASE}/repos/{owner}/{repo}/commits?per_page={limit}", None, pat)
    commits = []
    for item in items:
        commit = item.get("commit") or {}
        author = commit.get("author") or {}
        message = (commit.get("message") or "").splitlines()[0]
        commits.append({
            "sha": item.get("sha", "")[:7],
            "date": author.get("date"),
            "author": author.get("name"),
            "msg": message,
        })
    return commits


# --- Actions Secrets ---

def list_secrets(owner: str, repo: str, pat: str) -> list[dict]:
    """Actions Secret 목록을 반환한다."""
    data = _request("GET", f"{_API_BASE}/repos/{owner}/{repo}/actions/secrets?per_page=100", None, pat)
    return [
        {"name": item["name"], "updated_at": item.get("updated_at")}
        for item in data.get("secrets", [])
    ]


def _load_nacl_public():
    """PyNaCl을 로드한다. 없으면 한 번 설치를 시도한다."""
    try:
        from nacl import encoding, public
        return encoding, public
    except ImportError:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "PyNaCl", "-q"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            from nacl import encoding, public
            return encoding, public
        except Exception as e:
            raise PyNaClMissingError("PyNaCl을 사용할 수 없습니다. 수동 설치: pip install PyNaCl") from e


def _encrypt_secret(public_key: str, value: str) -> str:
    encoding, public = _load_nacl_public()
    public_key_obj = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key_obj)
    encrypted = sealed_box.encrypt(value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def set_secret(owner: str, repo: str, name: str, value: str, pat: str) -> dict:
    """Actions Secret을 암호화해 생성 또는 갱신한다."""
    key = _request("GET", f"{_API_BASE}/repos/{owner}/{repo}/actions/secrets/public-key", None, pat)
    encrypted_value = _encrypt_secret(key["key"], value)
    _request(
        "PUT",
        f"{_API_BASE}/repos/{owner}/{repo}/actions/secrets/{urllib.parse.quote(name, safe='')}",
        {"encrypted_value": encrypted_value, "key_id": key["key_id"]},
        pat,
    )
    return {"name": name, "status": "updated"}


def list_pulls(
    owner: str, repo: str, pat: str, state: str = "open",
) -> list[dict]:
    """PR 목록을 조회한다."""
    items = _request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/pulls?state={state}&per_page=50",
        None,
        pat,
    )
    return [
        {"number": i["number"], "title": i["title"], "url": i["html_url"], "state": i["state"]}
        for i in items
    ]


def search_issues(
    owner: str, repo: str, keyword: str, pat: str, per_page: int = 5,
) -> list[dict]:
    """레포 내 제목에 keyword가 포함된 이슈를 검색한다 (중복 이슈 판단용)."""
    q = urllib.parse.quote(f"is:issue repo:{owner}/{repo} in:title {keyword}", safe="")
    data = _request(
        "GET", f"{_API_BASE}/search/issues?q={q}&per_page={per_page}", None, pat
    )
    items = data.get("items", []) if isinstance(data, dict) else []
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "url": i["html_url"],
            "state": i["state"],
            "labels": [label["name"] for label in i.get("labels", [])],
        }
        for i in items
    ]


def update_pull_request(
    owner: str, repo: str, pr_number: int, pat: str,
    title: str | None = None, body: str | None = None,
    state: str | None = None, base: str | None = None,
) -> dict:
    """PR을 수정하고 {number, url}을 반환한다. PR 본문(릴리스 노트) 업데이트 등에 사용."""
    payload: dict = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state is not None:
        payload["state"] = state
    if base is not None:
        payload["base"] = base
    data = _request(
        "PATCH", f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}", payload, pat
    )
    return {"number": data["number"], "url": data["html_url"]}


def create_pull_request(
    owner: str, repo: str, title: str, body: str,
    head: str, base: str, pat: str,
) -> dict:
    """PR을 생성하고 {number, url}을 반환한다."""
    data = _request(
        "POST",
        f"{_API_BASE}/repos/{owner}/{repo}/pulls",
        {"title": title, "body": body, "head": head, "base": base},
        pat,
    )
    return {"number": data["number"], "url": data["html_url"]}


def merge_pull_request(
    owner: str, repo: str, pr_number: int, pat: str,
    merge_method: str = "merge", commit_title: str | None = None,
    commit_message: str | None = None, sha: str | None = None,
) -> dict:
    """PR을 머지한다.

    merge_method: merge(기본) / squash / rebase.
    머지 불가(405)·sha 불일치(409)·rebase 불허(422)는 GitHubAPIError로 올라오므로
    호출자(CLI 레이어)가 status_code로 verdict를 판정한다.
    반환: {sha, merged, message}.
    """
    payload: dict = {"merge_method": merge_method}
    if commit_title is not None:
        payload["commit_title"] = commit_title
    if commit_message is not None:
        payload["commit_message"] = commit_message
    if sha is not None:
        payload["sha"] = sha
    data = _request(
        "PUT",
        f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/merge",
        payload,
        pat,
    )
    return {
        "sha": data.get("sha"),
        "merged": data.get("merged", False),
        "message": data.get("message"),
    }


def get_pull_detail(owner: str, repo: str, pr_number: int, pat: str) -> dict:
    """단일 PR 상세에서 머지 판정에 필요한 필드를 추출한다.

    list_pulls에는 body·mergeable_state가 없어 deploy-status 검증용으로 별도 조회한다.
    """
    pr = _request("GET", f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}", None, pat)
    return {
        "number": pr["number"],
        "state": pr["state"],
        "merged": pr.get("merged", False),
        "mergeable_state": pr.get("mergeable_state"),
        "body": pr.get("body") or "",
        "head_sha": pr.get("head", {}).get("sha"),
        "url": pr["html_url"],
        "created_at": pr.get("created_at"),
        "updated_at": pr.get("updated_at"),
    }


def find_open_pr_by_base(owner: str, repo: str, base: str, pat: str) -> dict | None:
    """base 브랜치로 들어오는 open PR 중 첫 번째의 상세를 반환한다. 없으면 None.

    deploy-status를 --pr 없이 호출할 때 deploy PR을 자동으로 찾기 위함.
    """
    items = _request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/pulls?state=open&base={base}&per_page=50",
        None, pat,
    )
    if not items:
        return None
    return get_pull_detail(owner, repo, items[0]["number"], pat)


def get_branch_head(owner: str, repo: str, branch: str, pat: str) -> str | None:
    """브랜치 HEAD SHA를 반환한다. 브랜치가 없으면 None (404를 None으로 흡수)."""
    enc = urllib.parse.quote(branch, safe="")
    try:
        ref = _request("GET", f"{_API_BASE}/repos/{owner}/{repo}/git/ref/heads/{enc}", None, pat)
    except GitHubAPIError as e:
        if e.status_code == 404:
            return None
        raise
    return ref.get("object", {}).get("sha")


# --- GitHub Actions ---

def _run_summary(run: dict) -> dict:
    """workflow run 객체에서 요약 필드만 추출한다."""
    return {
        "run_id": run["id"],
        "name": run.get("name"),
        "path": run.get("path"),
        "branch": run.get("head_branch"),
        "event": run.get("event"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "created_at": (run.get("created_at") or "")[:16],
        "url": run.get("html_url"),
    }


def get_run(owner: str, repo: str, run_id: int, pat: str) -> dict:
    """단일 run 메타 + job 목록(실패 step 포함)을 반환한다."""
    run = _request("GET", f"{_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}", None, pat)
    result = _run_summary(run)
    jobs_data = _request(
        "GET", f"{_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs?per_page=100", None, pat
    )
    jobs = []
    failed_job_ids = []
    for j in jobs_data.get("jobs", []):
        failed_steps = [
            s["name"] for s in (j.get("steps") or []) if s.get("conclusion") == "failure"
        ]
        jobs.append({
            "job_id": j["id"],
            "name": j["name"],
            "conclusion": j.get("conclusion"),
            "failed_steps": failed_steps,
        })
        if j.get("conclusion") == "failure":
            failed_job_ids.append(j["id"])
    result["jobs"] = jobs
    result["failed_job_ids"] = failed_job_ids
    return result


def get_job_log(
    owner: str, repo: str, job_id: int, pat: str,
    grep: str = "error", tail: int = 30,
) -> dict:
    """job 로그를 받아 grep 매칭 라인의 끝 tail개를 반환한다.

    job logs 엔드포인트는 Azure로 redirect되므로 _request의 strip 핸들러가 필수.
    """
    text = _request(
        "GET", f"{_API_BASE}/repos/{owner}/{repo}/actions/jobs/{job_id}/logs", None, pat, raw=True
    )
    all_lines = text.splitlines()
    needle = grep.lower()
    matched = [l for l in all_lines if needle in l.lower()]
    return {
        "job_id": job_id,
        "total_lines": len(all_lines),
        "matched_count": len(matched),
        "grep": grep,
        "lines": [l[:300] for l in matched[-tail:]],
    }


def list_failed_runs(owner: str, repo: str, pat: str, limit: int = 10) -> list[dict]:
    """최근 실패(conclusion=failure) run 목록을 반환한다."""
    data = _request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/actions/runs?status=failure&per_page={limit}",
        None, pat,
    )
    return [_run_summary(r) for r in data.get("workflow_runs", [])]


def resolve_pr_runs(owner: str, repo: str, pr_number: int, pat: str) -> dict:
    """PR 번호 → head SHA → 연결된 run 목록을 반환한다."""
    pr = _request("GET", f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}", None, pat)
    head_sha = pr["head"]["sha"]
    head_ref = pr["head"]["ref"]
    runs = _request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/actions/runs?head_sha={head_sha}&per_page=30",
        None, pat,
    )
    return {
        "pr_number": pr_number,
        "head_sha": head_sha,
        "head_ref": head_ref,
        "runs": [_run_summary(r) for r in runs.get("workflow_runs", [])],
    }


def resolve_branch_runs(owner: str, repo: str, branch: str, pat: str, limit: int = 10) -> list[dict]:
    """브랜치명 → 해당 브랜치의 최근 run 목록을 반환한다."""
    enc = urllib.parse.quote(branch, safe="")
    data = _request(
        "GET",
        f"{_API_BASE}/repos/{owner}/{repo}/actions/runs?branch={enc}&per_page={limit}",
        None, pat,
    )
    return [_run_summary(r) for r in data.get("workflow_runs", [])]


# ── 증적 이미지 업로드 ─────────────────────────────────────────────────────
#
# GitHub이 이슈 첨부에 쓰는 업로드 엔드포인트는 **브라우저 세션이 필요해 PAT로 쓸 수 없다.**
# 그래서 릴리스 자산(Release assets)으로 우회한다. 실측으로 확인한 것:
#
#   - 익명 접근 200, Content-Type은 application/octet-stream (image/png가 아니다)
#   - Content-Disposition: attachment 가 붙지만 <img> 태그에서는 무시된다
#   - **X-Content-Type-Options(nosniff)가 없다** → 브라우저가 매직넘버로 스니핑해 그린다
#   - 이슈 본문·댓글 모두 <img>로 렌더링된다 (body_html로 확인)
#
# 레포에 커밋하는 방식은 쓰지 않는다 — 이미지가 git 히스토리에 영구히 남는다.

# 증적 전용 릴리스 태그. 버전 릴리스와 섞으면 릴리스 목록이 증적으로 뒤덮인다.
EVIDENCE_TAG = "qa-evidence"

# <img>로 렌더링되는 형식. 이 밖의 것(mp4 등)은 링크로만 남는다 —
# GitHub이 video로 그려주는 것은 공식 첨부 경로뿐이라 릴리스 자산은 해당되지 않는다.
_RENDERABLE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def _upload_request(url: str, data: bytes, content_type: str, pat: str) -> dict:
    """바이너리 본문을 올린다.

    _request는 Content-Type이 application/json으로 고정돼 있어 자산 업로드에 쓸 수 없다.
    """
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": content_type,
            "Content-Length": str(len(data)),
            "User-Agent": "projectops",
        },
    )
    try:
        with _opener.open(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.fp.read() if e.fp else b""
        try:
            msg = json.loads(body).get("message", str(e))
        except Exception:
            msg = body.decode("utf-8", "replace")[:200] or str(e)
        raise GitHubAPIError(e.code, msg) from e


def ensure_evidence_release(owner: str, repo: str, pat: str, tag: str = EVIDENCE_TAG) -> dict:
    """증적 릴리스를 확보한다. 없으면 만든다(멱등).

    prerelease로 만든다 — 최신 릴리스 배지가 증적으로 바뀌면 사용자가 혼란스럽다.
    """
    try:
        return _request("GET", f"{_API_BASE}/repos/{owner}/{repo}/releases/tags/{tag}", None, pat)
    except GitHubAPIError as e:
        if e.status_code != 404:
            raise
    return _request(
        "POST", f"{_API_BASE}/repos/{owner}/{repo}/releases",
        {
            "tag_name": tag,
            "name": "QA 증적 저장소",
            "body": ("테스트·QA 증적 이미지를 담는 전용 릴리스입니다. 코드 릴리스가 아닙니다.\n"
                     "이슈·PR 본문과 댓글에서 이미지로 참조됩니다."),
            "draft": False,
            "prerelease": True,
        },
        pat,
    )


def _asset_name(path: str, prefix: str | None = None) -> str:
    """자산 이름을 만든다. 같은 이름이 있으면 GitHub이 422로 거절하므로 시각을 붙여 고유화한다.

    영문·숫자·일부 기호만 남긴다 — 한글 파일명은 URL에서 인코딩돼 마크다운이 깨진다.
    """
    p = pathlib.PurePath(path)
    # 한글 파일명은 통째로 걸러지므로 "__2" 같은 찌꺼기가 남는다. 양끝 구분자를 걷어내고
    # 아무것도 안 남으면 image로 둔다 — 고유성은 어차피 시각이 보장한다.
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", p.stem)
    stem = re.sub(r"[-_.]{2,}", "-", stem).strip("-_.") or "image"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    head = f"{prefix}_" if prefix else ""
    return f"{head}{stamp}_{stem}{p.suffix.lower()}"


def upload_evidence_image(
    owner: str, repo: str, file_path: str, pat: str,
    tag: str = EVIDENCE_TAG, prefix: str | None = None,
) -> dict:
    """이미지 파일 하나를 증적 릴리스에 올리고 마크다운까지 만들어 돌려준다."""
    src = pathlib.Path(file_path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"파일이 없습니다: {src}")

    data = src.read_bytes()
    ctype = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
    name = _asset_name(src.name, prefix)

    rel = ensure_evidence_release(owner, repo, pat, tag)
    upload_url = rel["upload_url"].split("{")[0] + f"?name={urllib.parse.quote(name)}"
    asset = _upload_request(upload_url, data, ctype, pat)

    url = asset["browser_download_url"]
    renderable = src.suffix.lower() in _RENDERABLE
    return {
        "name": name,
        "url": url,
        "size": len(data),
        "content_type": ctype,
        # 렌더링되지 않는 형식을 ![]()로 넣으면 깨진 이미지가 뜬다. 링크로 준다.
        "markdown": f"![{src.stem}]({url})" if renderable else f"[{src.name}]({url})",
        "renderable": renderable,
        "asset_id": asset["id"],
    }


def delete_release_asset(owner: str, repo: str, asset_id: int, pat: str) -> None:
    """올린 증적을 지운다. 검증용으로 올린 것을 치울 때 쓴다."""
    _request("DELETE", f"{_API_BASE}/repos/{owner}/{repo}/releases/assets/{asset_id}", None, pat)


def is_repo_private(owner: str, repo: str, pat: str) -> bool:
    """private 레포인지. private이면 익명 접근이 막혀 이미지가 렌더링되지 않는다."""
    return bool(_request("GET", f"{_API_BASE}/repos/{owner}/{repo}", None, pat).get("private"))

