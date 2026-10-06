#!/usr/bin/env python3
"""릴리스가 나가면 완료된 이슈를 닫는다 (#771) — stdlib 전용.

"완료해도 닫지 않고 라벨로만 표시한다"는 정책은 Projects 동기화가 라벨 기반이라서 생겼다.
그 결과 열린 이슈가 쌓여 방문자에게는 방치된 프로젝트로 보인다. 그래서 사람이 닫는 대신
**릴리스가 나갈 때 워크플로우가 닫는다.** 완료 표시는 라벨이 그대로 맡는다.

규칙
  - 릴리스 구간(before..after) 커밋 메시지가 참조한 이슈 URL만 대상으로 한다.
  - 완료 라벨(status: done / 작업완료)이 붙은 이슈만 닫는다. 라벨이 없으면 건드리지 않는다.
  - 이미 닫혔거나 PR이면 건너뛴다.
  - version.yml 의 close_on_release 가 true 일 때만 동작한다. 키가 없으면(기존 설치) 아무것도 하지 않는다.

사용:
  close_issues_on_release.py --repo owner/name --before SHA --after SHA [--dry-run]
환경: GITHUB_TOKEN
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
DONE_LABELS = {"status: done", "작업완료"}


def close_on_release_enabled(version_yml_text: str) -> bool:
    """version.yml 에서 close_on_release 값을 읽는다. 키가 없으면 False (기존 설치 보호)."""
    m = re.search(r"^\s+close_on_release:\s*[\"']?(true|false)[\"']?", version_yml_text, re.M)
    return bool(m) and m.group(1) == "true"


def issue_numbers_from_commits(messages: list[str], repo: str) -> list[int]:
    """커밋 메시지에서 이 저장소의 이슈 URL 번호를 모은다 (등장 순서 유지, 중복 제거)."""
    pat = re.compile(rf"github\.com/{re.escape(repo)}/issues/(\d+)", re.I)
    seen: list[int] = []
    for msg in messages:
        for n in pat.findall(msg):
            if int(n) not in seen:
                seen.append(int(n))
    return seen


def should_close(issue: dict) -> bool:
    """닫을 이슈인가: 이슈(PR 아님)이고 열려 있고 완료 라벨이 있다."""
    if "pull_request" in issue or issue.get("state") != "open":
        return False
    names = {(l["name"] if isinstance(l, dict) else l) for l in issue.get("labels", [])}
    return bool(names & DONE_LABELS)


def _request(method: str, url: str, token: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "Content-Type": "application/json", "User-Agent": "projectops-close-on-release",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def previous_release_tag(after: str) -> str:
    """after 에 닿는 태그 중, after 자신을 가리키지 않는 가장 최근 것 (직전 릴리스).

    dispatch 로 깨워질 때는 before 가 없다(#551). 마지막 커밋만 보면 릴리스 뒤에 붙는
    README 버전 커밋만 보게 되므로 직전 릴리스 태그부터 현재까지를 구간으로 삼는다.
    """
    head = _git("rev-parse", after)
    for tag in _git("tag", "--merged", after, "--sort=-creatordate").splitlines():
        if _git("rev-list", "-n", "1", tag) != head:
            return tag
    return ""


def release_range(before: str, after: str) -> str:
    if before and set(before) != {"0"}:
        return f"{before}..{after}"
    tag = previous_release_tag(after)
    return f"{tag}..{after}" if tag else f"{after}~1..{after}"


def commit_messages(before: str, after: str) -> list[str]:
    out = _git("log", release_range(before, after), "--format=%B%x00")
    return [m for m in out.split("\x00") if m.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--before", default="")
    ap.add_argument("--after", required=True)
    ap.add_argument("--version-file", default="version.yml")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    try:
        text = open(a.version_file, encoding="utf-8").read()
    except OSError:
        text = ""
    if not close_on_release_enabled(text):
        print("close_on_release 가 켜져 있지 않아 건너뜁니다.")
        return 0

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("GITHUB_TOKEN 이 없어 건너뜁니다.")
        return 0

    numbers = issue_numbers_from_commits(commit_messages(a.before, a.after), a.repo)
    print(f"릴리스 구간이 참조한 이슈: {numbers}")
    closed = []
    for n in numbers:
        try:
            issue = _request("GET", f"{API}/repos/{a.repo}/issues/{n}", token)
        except urllib.error.HTTPError as e:
            print(f"#{n}: 조회 실패 ({e.code}) — 건너뜀")
            continue
        if not should_close(issue):
            print(f"#{n}: 건너뜀 (열린 이슈가 아니거나 완료 라벨 없음)")
            continue
        if a.dry_run:
            print(f"#{n}: [dry-run] 닫을 대상")
            continue
        try:
            _request("PATCH", f"{API}/repos/{a.repo}/issues/{n}", token,
                     {"state": "closed", "state_reason": "completed"})
            closed.append(n)
            print(f"#{n}: 닫음")
        except urllib.error.HTTPError as e:
            print(f"#{n}: 닫기 실패 ({e.code})")
    print(f"닫은 이슈: {closed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
