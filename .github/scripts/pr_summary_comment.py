#!/usr/bin/env python3
"""
pr_summary_comment.py

PR 변경 요약을 댓글로 올린다. 표식으로 기존 댓글을 찾아 **갱신**하므로 커밋을 여러 번
올려도 요약 댓글은 하나로 유지된다 (이슈 #553).

왜 갱신인가: PR에 커밋을 추가할 때마다 새 댓글이 달리면 스레드가 요약으로 도배되어 정작
사람이 쓴 리뷰 코멘트가 묻힌다. 표식은 HTML 주석이라 렌더링되지 않는다.

입력은 provider 사다리가 만든 pr_body.md다. 그 파일은 릴리스 노트 형식(`Summary by
CodeRabbit` 헤더 + `## 릴리스 노트`)으로 감싸여 있는데, PR 댓글에는 그 껍데기가 어울리지
않으므로 본문만 꺼내 다시 감싼다.

  - 출력: 언제나 JSON 한 줄(stdout). 사람이 읽을 로그는 stderr.
  - 어떤 실패도 exit 0 — 요약 댓글 때문에 PR이 막히면 안 된다.

사용 예:
  GITHUB_TOKEN=... python3 pr_summary_comment.py --repo owner/name --pr 12 \\
      --body-file pr_body.md --app-release true
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

MARKER = "<!-- PROJECTOPS-AI-SUMMARY -->"

# 앱 심사로 이어지는 레포에서만 붙는 안내. 리뷰어가 무게를 다르게 잡도록 한다.
APP_RELEASE_NOTICE = (
    "> 📱 이 저장소는 앱스토어·플레이스토어 심사로 이어집니다. "
    "이 변경은 다음 릴리스에 포함되어 심사에 들어갑니다."
)


def extract_body(raw: str) -> str:
    """릴리스 노트 껍데기에서 항목 본문만 꺼낸다.

    provider 사다리는 `## 릴리스 노트` 아래에 항목을 쓰고 HTML 주석으로 감싼다.
    구조가 달라지면(다른 provider 등) 원문을 그대로 쓴다 — 요약이 없는 것보다는 낫다.
    """
    m = re.search(r"##\s*릴리스 노트\s*\n(.*?)(?:\n<!--|\Z)", raw, re.S)
    body = m.group(1) if m else raw
    # 주변 HTML 주석 줄 제거 (남아 있으면 댓글에 빈 줄만 생긴다)
    body = "\n".join(l for l in body.split("\n") if not l.strip().startswith("<!--"))
    return body.strip()


def build_comment(raw: str, app_release: bool) -> str:
    parts = [MARKER, "", "## 🤖 변경 요약", ""]
    if app_release:
        parts += [APP_RELEASE_NOTICE, ""]
    parts += [extract_body(raw), "", "---",
              "<sub>커밋 내역을 자동 요약한 내용입니다. 새 커밋이 올라오면 이 댓글이 갱신됩니다.</sub>"]
    return "\n".join(parts)


def _req(url: str, token: str, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "projectops-pr-summary",
    })
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def find_existing(repo: str, pr: int, token: str) -> int | None:
    """표식을 가진 기존 요약 댓글의 id. 없으면 None."""
    page = 1
    while page <= 10:  # 댓글이 아주 많은 PR에서도 멈추도록 상한을 둔다
        items = _req(f"https://api.github.com/repos/{repo}/issues/{pr}/comments"
                     f"?per_page=100&page={page}", token) or []
        for c in items:
            if MARKER in (c.get("body") or ""):
                return c.get("id")
        if len(items) < 100:
            return None
        page += 1
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pr_summary_comment")
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--app-release", default="false")
    args = parser.parse_args(argv)

    out = {"ok": False, "action": None, "comment_id": None, "summary": "", "next": None}
    token = os.environ.get("GITHUB_TOKEN", "")

    try:
        raw = open(args.body_file, encoding="utf-8").read()
    except Exception as e:
        out["summary"] = f"요약 파일을 읽지 못했습니다: {e}"
        sys.stderr.write(out["summary"] + "\n")
        print(json.dumps(out, ensure_ascii=False))
        return 0

    if not token:
        out["summary"] = "GITHUB_TOKEN이 없어 댓글을 올리지 못했습니다"
        sys.stderr.write(out["summary"] + "\n")
        print(json.dumps(out, ensure_ascii=False))
        return 0

    body = build_comment(raw, str(args.app_release).lower() == "true")

    try:
        existing = find_existing(args.repo, args.pr, token)
        if existing:
            res = _req(f"https://api.github.com/repos/{args.repo}/issues/comments/{existing}",
                       token, "PATCH", {"body": body})
            out.update(ok=True, action="updated", comment_id=existing,
                       summary=f"기존 요약 댓글 갱신 (#{existing})")
        else:
            res = _req(f"https://api.github.com/repos/{args.repo}/issues/{args.pr}/comments",
                       token, "POST", {"body": body})
            out.update(ok=True, action="created", comment_id=(res or {}).get("id"),
                       summary="요약 댓글 작성")
    except urllib.error.HTTPError as e:
        out["summary"] = f"댓글 처리 실패: HTTP {e.code} {e.reason}"
    except Exception as e:
        out["summary"] = f"댓글 처리 실패: {type(e).__name__}: {e}"

    sys.stderr.write(out["summary"] + "\n")
    print(json.dumps(out, ensure_ascii=False))
    return 0  # 요약 댓글 때문에 PR을 막지 않는다


if __name__ == "__main__":
    sys.exit(main())
