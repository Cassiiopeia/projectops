"""repo-update: 레포 About·topics·Discussions 변경 (before 읽기 > 계획·검증 > --dry-run 이면 계획만 > 적용 > after 검증)
승인 후에만 호출. 구현하지 않는 것: 가시성 변경, 레포 삭제·이름 변경·아카이브, 기본 브랜치 변경
"""
from __future__ import annotations

import re

from common import gh_client

from oss_consult import github_api
from oss_consult.github_api import _get
from oss_consult.output import _api_fail, _bad_slug, _fail, _no_pat, _out, _split

# 공식 문서 확인: 토픽은 소문자·숫자·하이픈, 50자 이하, 레포당 20개 이하
# (docs.github.com/.../classifying-your-repository-with-topics). About 설명 350자는 검색으로만 확인 — 확인 필요.
_TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
MAX_TOPICS = 20
MAX_DESCRIPTION = 350


def _write_repo_state(owner: str, repo: str, pat: str) -> dict:
    meta = _get(f"/repos/{owner}/{repo}", pat)
    topics = _get(f"/repos/{owner}/{repo}/topics", pat).get("names", meta.get("topics", []))
    return {"description": meta.get("description"), "homepage": meta.get("homepage") or None,
            "topics": topics, "has_discussions": meta.get("has_discussions", False)}


def plan_repo_update(before: dict, args) -> tuple[dict, str | None]:
    """바꿀 값만 계획으로 돌려준다. 검증 실패면 (빈 계획, 오류 메시지)."""
    plan: dict = {}
    if args.description is not None:
        if not args.description.strip():
            return {}, "description 을 비우는 변경은 지원하지 않는다 (삭제성 변경은 제안만 한다)"
        if len(args.description) > MAX_DESCRIPTION:
            return {}, f"description 은 {MAX_DESCRIPTION}자 이하여야 한다 (현재 {len(args.description)}자)"
        if args.description != (before["description"] or ""):
            plan["description"] = args.description
    if args.homepage is not None:
        if not re.match(r"^https?://\S+$", args.homepage):
            return {}, "homepage 는 http(s):// URL 이어야 한다 (값을 비우는 변경은 지원하지 않는다)"
        if args.homepage != (before["homepage"] or ""):
            plan["homepage"] = args.homepage
    if args.topics is not None:
        new = [t.strip().lower() for t in args.topics.split(",") if t.strip()]
        if not new and args.topics_mode == "replace":
            return {}, "topics 를 전부 비우는 교체는 지원하지 않는다 (삭제성 변경은 제안만 한다)"
        bad = [t for t in new if not _TOPIC_RE.match(t)]
        if bad:
            return {}, f"토픽은 소문자·숫자·하이픈, 50자 이하여야 한다: {', '.join(bad)}"
        merged = list(dict.fromkeys(new if args.topics_mode == "replace" else before["topics"] + new))
        if len(merged) > MAX_TOPICS:
            return {}, f"토픽은 레포당 {MAX_TOPICS}개 이하여야 한다 (계획 {len(merged)}개)"
        if merged != before["topics"]:
            plan["topics"] = merged
    if args.discussions is not None:
        want = args.discussions == "on"
        if want != before["has_discussions"]:
            plan["has_discussions"] = want
    return plan, None


def cmd_repo_update(args) -> int:
    target = _split(args.target)
    if not target:
        return _bad_slug()
    owner, repo = target
    if all(getattr(args, k) is None for k in ("description", "homepage", "topics", "discussions")):
        return _fail("nothing_to_change", "바꿀 항목이 없다",
                     "--description, --homepage, --topics, --discussions 중 하나 이상을 준다")
    pat = github_api._pat(owner, repo)
    if not pat:
        return _no_pat()
    try:
        before = _write_repo_state(owner, repo, pat)
    except (gh_client.GitHubAPIError, gh_client.GitHubNetworkError) as e:
        return _api_fail(e, pat)
    plan, err = plan_repo_update(before, args)
    if err:
        return _fail("invalid_input", err, "입력을 고쳐 다시 실행한다", pat, before=before)
    if not plan:
        return _out({"code": "no_change", "data": {"repo": f"{owner}/{repo}", "before": before, "planned": {}},
                     "summary": "이미 원하는 상태다 — 바꿀 것이 없다", "next": "다음 조치로 넘어간다"}, pat)
    if args.dry_run:
        return _out({"data": {"repo": f"{owner}/{repo}", "dry_run": True, "before": before, "planned": plan},
                     "summary": "계획만 출력(--dry-run). 적용하지 않았다",
                     "next": "사용자 승인을 받은 뒤 --dry-run 없이 같은 명령을 실행한다"}, pat)
    applied: list[str] = []
    try:
        patch = {k: plan[k] for k in ("description", "homepage", "has_discussions") if k in plan}
        if patch:
            github_api._call("PATCH", f"/repos/{owner}/{repo}", pat, patch)
            applied += list(patch)
        if "topics" in plan:
            github_api._call("PUT", f"/repos/{owner}/{repo}/topics", pat, {"names": plan["topics"]})
            applied.append("topics")
    except (gh_client.GitHubAPIError, gh_client.GitHubNetworkError) as e:
        # 일부만 적용됐을 수 있다 — before 로 되돌릴 수 있게 알린다
        return _api_fail(e, pat, before=before, applied=applied)
    try:
        after = _write_repo_state(owner, repo, pat)
    except (gh_client.GitHubAPIError, gh_client.GitHubNetworkError) as e:
        return _api_fail(e, pat, before=before, applied=applied)
    # has_discussions 는 공식 PATCH 문서에서 확인하지 못했다(확인 필요) — 반영됐는지 다시 읽어 검증한다
    warnings = [f"{k} 가 적용 후에도 {after.get(k)!r} 이다 — 이 필드는 API 로 반영되지 않을 수 있다"
                for k in plan if k != "topics" and after.get(k) != plan[k]
                and not (k in ("description", "homepage") and (after.get(k) or "") == plan[k])]
    return _out({"data": {"repo": f"{owner}/{repo}", "dry_run": False, "before": before, "planned": plan,
                          "after": after, "warnings": warnings},
                 "summary": f"적용: {', '.join(applied)}" + (" — 일부 미반영 경고" if warnings else ""),
                 "next": "collect 를 다시 불러 변화를 확인한다. 되돌리려면 before 값으로 repo-update 를 다시 실행한다"}, pat)
