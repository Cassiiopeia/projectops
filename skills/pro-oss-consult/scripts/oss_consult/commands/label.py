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
        return _fail("invalid_input", "--name is required", "Pass the target label with --name")
    color = (args.color or "").lstrip("#").lower() or None
    if color and not _COLOR_RE.match(color):
        return _fail("invalid_input", f"--color must be a 6-digit hex value: {args.color}", "Example: --color ededed")
    if args.description is not None and len(args.description) > MAX_LABEL_DESCRIPTION:
        return _fail("invalid_input", f"Label description must be {MAX_LABEL_DESCRIPTION} characters or fewer", "Shorten the description and run again")
    new_name = (args.new_name or "").strip() or None
    if action == "rename" and not new_name:
        return _fail("invalid_input", "rename requires --new-name", "Pass the new name with --new-name")
    if action == "recolor" and not color:
        return _fail("invalid_input", "recolor requires --color", "Pass the new color with --color")
    if action in ("rename", "recolor") and name in PROTECTED_LABELS:
        return _fail("protected_label", f"'{name}' is a projectops status label, so it is not changed",
                     "Projects board sync is tied to this name. Pick another label or let the user change it by hand")
    if action == "rename" and new_name in PROTECTED_LABELS:
        return _fail("protected_label", f"'{new_name}' is a projectops status label name, so no label is renamed to it",
                     "Pick a different new name")
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
            return _fail("label_exists", f"Label already exists: {old['name']}", "Use another name, or change it with rename or recolor", pat, before=old)
        body = {"name": name, "color": color or "ededed"}
        if args.description is not None:
            body["description"] = args.description
        method, path = "POST", f"/repos/{owner}/{repo}/labels"
    else:
        if not old:
            return _fail("label_not_found", f"Label not found: {name}", "Check the label name (labels.names in collect)", pat)
        if action == "rename":
            clash = by_lower.get(new_name.lower())
            # 대소문자만 바꾸는 이름 변경은 같은 라벨이므로 허용한다
            if clash and clash["name"].lower() != old["name"].lower():
                return _fail("label_exists", f"The new name already exists: {clash['name']}",
                             "Use another name. To merge, the user moves the issue labels and cleans up by hand", pat, before=old)
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
                     "summary": "Plan only (--dry-run). Nothing was applied",
                     "next": "After the user approves, run the same command without --dry-run"}, pat)
    try:
        after = github_api._call(method, path, pat, body)
    except (gh_client.GitHubAPIError, gh_client.GitHubNetworkError) as e:
        return _api_fail(e, pat, before=old)
    return _out({"data": {"repo": f"{owner}/{repo}", "dry_run": False, "action": action, "before": old,
                          "after": {k: after.get(k) for k in ("name", "color", "description")}},
                 "summary": f"Label {action} done: {name}",
                 "next": "To undo, run the same subcommand again with the before values (labels on existing issues are kept)"}, pat)
