#!/usr/bin/env python3
"""
dispatch_downstream.py

기본 토큰(GITHUB_TOKEN)으로 릴리스 PR을 머지했을 때, 원래 base 브랜치 push로 돌았어야 할
후속 워크플로우를 명시적으로 깨운다 (이슈 #551).

왜 필요한가: GitHub은 GITHUB_TOKEN이 만든 push로는 워크플로우를 다시 트리거하지 않는다
(무한 루프 방지). PAT로 머지하면 이 제약이 없으므로 이 스크립트를 돌릴 필요가 없다.
반면 workflow_dispatch 이벤트는 GITHUB_TOKEN으로도 트리거할 수 있다 — 그 점을 이용한다.

대상은 고정 목록이 아니라 레포에 실제로 설치된 워크플로우에서 찾는다. 프로젝트 타입마다
배포 워크플로우가 다르기 때문이다. 두 조건을 모두 만족해야 깨운다:
  1) base 브랜치 push로 트리거되는가  — 원래 돌았어야 할 대상인가
  2) workflow_dispatch를 지원하는가   — 깨울 수단이 있는가

2)를 만족하지 않으면 깨울 방법이 없다. 조용히 넘기지 않고 이름을 출력해 사용자가 판단하게 한다.

  - 커맨드: scan | dispatch
  - 출력: 언제나 JSON (ok / 데이터 / next)

사용 예:
  python3 dispatch_downstream.py scan --branch main
  GITHUB_TOKEN=... python3 dispatch_downstream.py dispatch --repo owner/name --branch main
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

WORKFLOWS_DIR = Path(".github/workflows")

# 자기 자신은 릴리스 PR 이벤트로 도는 워크플로우라 push 대상이 아니다. 혹시 이름이 바뀌어도
# 아래 트리거 판정(push+branch)에서 걸러지지만, 의도를 남겨둔다.
SELF = "PROJECT-COMMON-RELEASE-CHANGELOG"

# 깨우면 안 되는 워크플로우 — push로 도는 것이 맞지만 "릴리스 머지 직후"에 돌면 해로운 것들.
#
# VERSION-CONTROL: "릴리스 PR을 거치지 않은 main 직접 push"에만 발동해야 하는 안전망이다.
#   릴리스 머지 후 깨우는 것은 설계 의도에 정면으로 반한다. 이 워크플로우의 가드는
#   github.event.before가 없으면 HEAD^..HEAD만 검사하는데, dispatch에는 before가 없다.
#   README 갱신 같은 후속 커밋이 먼저 들어오면 그 범위에 version.yml이 없어 가드가 뚫리고
#   버전이 한 번 더 올라간다. 순서에 기대지 않고 아예 제외한다.
EXCLUDE = {"PROJECT-COMMON-VERSION-CONTROL"}


def _strip_comments(text: str) -> str:
    """주석 줄 제거 — 주석 안의 예시 트리거를 실제 트리거로 오인하지 않도록."""
    return "\n".join(l for l in text.split("\n") if not re.match(r"^\s*#", l))


def parse_triggers(text: str, branch: str) -> dict:
    """워크플로우 YAML에서 필요한 트리거 정보만 뽑는다.

    정식 YAML 파서를 쓰지 않는 이유: 이 레포의 워크플로우에는 0칸 들여쓰기 heredoc이 들어 있어
    엄격한 파서가 파싱에 실패한다(GitHub 본체는 정상 처리). 여기서는 트리거 블록만 보면 되므로
    줄 단위 스캔이 더 안전하다.
    """
    body = _strip_comments(text)
    lines = body.split("\n")

    has_dispatch = any(re.match(r"^\s*workflow_dispatch:", l) for l in lines)

    # on: 블록 안의 push: 하위 branches 목록을 찾는다.
    in_on = False
    in_push = False
    push_branches: list[str] = []
    for line in lines:
        if re.match(r"^on:", line):
            in_on = True
            continue
        if in_on and re.match(r"^[a-zA-Z_]", line):  # 최상위 다른 키 → on 블록 종료
            in_on = False
            in_push = False
        if not in_on:
            continue
        if re.match(r"^\s{2}push:", line):
            in_push = True
            continue
        if in_push and re.match(r"^\s{2}[a-zA-Z_]+:", line):  # push와 같은 깊이의 다른 이벤트
            in_push = False
        if in_push:
            m = re.search(r"branches:\s*\[(.*?)\]", line)
            if m:
                push_branches += [b.strip().strip("\"'") for b in m.group(1).split(",") if b.strip()]

    return {
        "workflow_dispatch": has_dispatch,
        "push_branches": push_branches,
        "on_push_branch": branch in push_branches,
    }


def scan(branch: str, workflows_dir: Path = WORKFLOWS_DIR) -> dict:
    """설치된 워크플로우를 훑어 깨울 대상과 깨울 수 없는 대상을 가른다."""
    targets, unreachable = [], []
    if workflows_dir.is_dir():
        for path in sorted(workflows_dir.iterdir()):
            if not path.is_file() or path.suffix not in (".yaml", ".yml"):
                continue
            if path.stem == SELF or path.stem in EXCLUDE:
                continue
            try:
                info = parse_triggers(path.read_text(encoding="utf-8"), branch)
            except Exception:
                continue
            if not info["on_push_branch"]:
                continue
            (targets if info["workflow_dispatch"] else unreachable).append(path.name)
    return {"targets": targets, "unreachable": unreachable}


def _dispatch_one(repo: str, token: str, filename: str, ref: str) -> tuple[bool, str]:
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{filename}/dispatches"
    data = json.dumps({"ref": ref}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "projectops-dispatch-downstream",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return (200 <= resp.status < 300), f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} {e.reason}"
    except Exception as e:  # 네트워크 오류 등 — 릴리스 자체를 실패시키지 않는다
        return False, f"{type(e).__name__}: {e}"


def _notify_pr(repo: str, pr: str, token: str, out: dict) -> None:
    """dispatch가 전량 실패하면 릴리스 PR에 알린다 (#555).

    PAT가 없는 저장소에서 dispatch는 후속 워크플로우를 깨우는 유일한 수단이다. 전부 실패하면
    배포·동기화가 통째로 누락되는데, 로그만 남기면 아무도 모른 채 지나간다.
    """
    if not (repo and pr and token):
        return
    lines = [
        "⚠️ **릴리스 후속 워크플로우를 자동 실행하지 못했습니다**",
        "",
        "이 저장소에는 PAT(`_GITHUB_PAT_TOKEN`)가 등록되어 있지 않아, 릴리스 머지 후 후속",
        "워크플로우를 직접 깨우는 경로를 사용합니다. 그 호출이 전부 실패했습니다.",
        "",
        "| 워크플로우 | 사유 |",
        "|---|---|",
    ]
    for item in out.get("failed", []):
        lines.append(f"| `{item['workflow']}` | {item['detail']} |")
    lines += [
        "",
        "**확인할 것**",
        "- 저장소 Settings > Actions > General > Workflow permissions가 "
        "`Read and write permissions`인지",
        "- 위 워크플로우들을 Actions 탭에서 수동 실행(Run workflow)하면 이번 릴리스분이 반영됩니다",
    ]
    payload = json.dumps({"body": "\n".join(lines)}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{pr}/comments",
        data=payload, method="POST", headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "projectops-dispatch-downstream",
        })
    try:
        urllib.request.urlopen(req)
        sys.stderr.write("  ℹ️ 실패 사실을 릴리스 PR에 알렸습니다\n")
    except Exception as e:  # 알림 실패가 릴리스를 막아선 안 된다
        sys.stderr.write(f"  ⚠️ PR 알림 실패: {type(e).__name__}\n")


def _log(out: dict) -> None:
    """Actions 로그에서 바로 읽히도록 결과를 사람 말로 풀어 stderr에 쓴다."""
    w = sys.stderr.write
    for item in out.get("dispatched", []):
        w(f"  ✅ 트리거: {item['workflow']}\n")
    for item in out.get("failed", []):
        w(f"  ⚠️ 트리거 실패: {item['workflow']} ({item['detail']})\n")
    for name in out.get("unreachable", []):
        w(f"  ⚠️ 깨울 수 없음(workflow_dispatch 미지원): {name}\n")
        w("     이 워크플로우는 PAT 없이는 릴리스 후 자동 실행되지 않습니다.\n")
    w(f"{out.get('summary', '')}\n")


def cmd_scan(args) -> int:
    result = scan(args.branch)
    result["ok"] = True
    result["summary"] = f"깨울 대상 {len(result['targets'])}개 / 깨울 수 없음 {len(result['unreachable'])}개"
    result["next"] = "dispatch" if result["targets"] else None
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_dispatch(args) -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    found = scan(args.branch)
    dispatched, failed = [], []

    if not token:
        out = {"ok": False, "code": "missing_token", "dispatched": [], "failed": [],
               "unreachable": found["unreachable"],
               "summary": "GITHUB_TOKEN이 없어 후속 워크플로우를 깨우지 못했습니다", "next": None}
        _log(out)
        print(json.dumps(out, ensure_ascii=False))
        return 0  # 릴리스는 이미 끝났다 — 여기서 실패로 파이프라인을 막지 않는다

    for filename in found["targets"]:
        ok, detail = _dispatch_one(args.repo, token, filename, args.branch)
        (dispatched if ok else failed).append({"workflow": filename, "detail": detail})

    out = {
        "ok": not failed,
        "dispatched": dispatched,
        "failed": failed,
        "unreachable": found["unreachable"],
        "summary": f"{len(dispatched)}개 트리거 / 실패 {len(failed)}개 / 깨울 수 없음 {len(found['unreachable'])}개",
        "next": None,
    }
    # 사람이 읽을 로그는 stderr로 — stdout은 JSON 한 줄이라는 계약을 지킨다.
    _log(out)
    # 하나도 못 깨웠으면 조용히 넘기지 않는다 (#555)
    if failed and not dispatched:
        _notify_pr(args.repo, os.environ.get("PR_NUMBER", ""), token, out)
    print(json.dumps(out, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dispatch_downstream")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="깨울 후속 워크플로우 탐색 (네트워크 없음)")
    p_scan.add_argument("--branch", required=True, help="base 브랜치 (예: main)")

    p_dispatch = sub.add_parser("dispatch", help="탐색 후 workflow_dispatch 트리거")
    p_dispatch.add_argument("--repo", required=True, help="owner/name")
    p_dispatch.add_argument("--branch", required=True, help="base 브랜치 (예: main)")

    args = parser.parse_args(argv)
    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "dispatch":
        return cmd_dispatch(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
