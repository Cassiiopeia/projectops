"""label: 라벨 생성·이름 변경·색 변경 (입력 검증 > 기존 라벨 읽기 > 계획 > --dry-run 이면 계획만 > 적용)
승인 후에만 호출. 라벨 삭제·이슈 닫기는 구현하지 않음
"""
from __future__ import annotations

import re
import urllib.parse

from common import gh_client

from oss_consult import github_api
from oss_consult.github_api import _label_records
from oss_consult.output import _api_fail, _bad_slug, _fail, _no_pat, _out, _split

MAX_LABEL_DESCRIPTION = 100
# projectops 한글 상태 라벨은 Projects 보드 동기화가 이름에 묶여 있다 — 코드 차원에서 건드리지 않는다
PROTECTED_LABELS = {"작업전", "작업중", "담당자확인", "피드백", "작업완료", "보류", "취소", "긴급", "문서",
                    # 영문 표준(#776) — 전환 기간에는 한글과 영문을 둘 다 보호한다
                    "status: todo", "status: in progress", "status: needs review", "status: feedback",
                    "status: done", "status: on hold", "status: cancelled", "priority: urgent", "documentation"}
_COLOR_RE = re.compile(r"^[0-9a-f]{6}$")


def cmd_label(args) -> int:
    target = _split(args.target)
    if not target:
        return _bad_slug()
    owner, repo = target
    action, name = args.action, (args.name or "").strip()
    if not name:
        return _fail("invalid_input", "--name 이 필요하다", "--name 으로 대상 라벨을 준다")
    color = (args.color or "").lstrip("#").lower() or None
    if color and not _COLOR_RE.match(color):
        return _fail("invalid_input", f"--color 는 6자리 16진수여야 한다: {args.color}", "예: --color ededed")
    if args.description is not None and len(args.description) > MAX_LABEL_DESCRIPTION:
        return _fail("invalid_input", f"라벨 설명은 {MAX_LABEL_DESCRIPTION}자 이하여야 한다", "설명을 줄여 다시 실행한다")
    new_name = (args.new_name or "").strip() or None
    if action == "rename" and not new_name:
        return _fail("invalid_input", "rename 은 --new-name 이 필요하다", "--new-name 으로 새 이름을 준다")
    if action == "recolor" and not color:
        return _fail("invalid_input", "recolor 는 --color 가 필요하다", "--color 로 새 색을 준다")
    if action in ("rename", "recolor") and name in PROTECTED_LABELS:
        return _fail("protected_label", f"'{name}' 은 projectops 상태 라벨이라 바꾸지 않는다",
                     "Projects 보드 동기화가 이 이름에 묶여 있다. 다른 라벨을 고르거나 사용자가 직접 바꾼다")
    if action == "rename" and new_name in PROTECTED_LABELS:
        return _fail("protected_label", f"'{new_name}' 은 projectops 상태 라벨 이름이라 이 이름으로 바꾸지 않는다",
                     "다른 새 이름을 고른다")
    pat = github_api._pat(owner, repo)
    if not pat:
        return _no_pat()
    try:
        rows, capped = _label_records(owner, repo, pat)
    except (gh_client.GitHubAPIError, gh_client.GitHubNetworkError) as e:
        return _api_fail(e, pat)
    by_lower = {r["name"].lower(): r for r in rows}
    old = by_lower.get(name.lower())
    if action == "create":
        if old:
            return _fail("label_exists", f"이미 있는 라벨이다: {old['name']}", "다른 이름을 쓰거나 rename·recolor 로 고친다", pat, before=old)
        body = {"name": name, "color": color or "ededed"}
        if args.description is not None:
            body["description"] = args.description
        method, path = "POST", f"/repos/{owner}/{repo}/labels"
    else:
        if not old:
            return _fail("label_not_found", f"없는 라벨이다: {name}", "라벨 이름을 확인한다 (collect 의 labels.names)", pat)
        if action == "rename":
            clash = by_lower.get(new_name.lower())
            # 대소문자만 바꾸는 이름 변경은 같은 라벨이므로 허용한다
            if clash and clash["name"].lower() != old["name"].lower():
                return _fail("label_exists", f"바꾸려는 이름이 이미 있다: {clash['name']}",
                             "다른 이름을 쓴다. 합치려면 사용자가 이슈 라벨을 옮긴 뒤 직접 정리한다", pat, before=old)
            body = {"new_name": new_name}
            if color:
                body["color"] = color
            if args.description is not None:
                body["description"] = args.description
        else:
            body = {"color": color}
        method, path = "PATCH", f"/repos/{owner}/{repo}/labels/{urllib.parse.quote(old['name'], safe='')}"
    if args.dry_run:
        return _out({"data": {"repo": f"{owner}/{repo}", "dry_run": True, "action": action, "before": old,
                              "planned": {"method": method, "path": path, "body": body}},
                     "summary": "계획만 출력(--dry-run). 적용하지 않았다",
                     "next": "사용자 승인을 받은 뒤 --dry-run 없이 같은 명령을 실행한다"}, pat)
    try:
        after = github_api._call(method, path, pat, body)
    except (gh_client.GitHubAPIError, gh_client.GitHubNetworkError) as e:
        return _api_fail(e, pat, before=old)
    return _out({"data": {"repo": f"{owner}/{repo}", "dry_run": False, "action": action, "before": old,
                          "after": {k: after.get(k) for k in ("name", "color", "description")}},
                 "summary": f"라벨 {action} 완료: {name}",
                 "next": "되돌리려면 before 값으로 같은 서브커맨드를 다시 실행한다 (기존 이슈의 라벨은 유지된다)"}, pat)
