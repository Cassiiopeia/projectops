"""list-repos: 계정·조직 레포 목록 (기본: 공개·비포크·비보관, 계정 소유만)
"""
from __future__ import annotations

from collections import Counter

from common import gh_client

from oss_consult import github_api
from oss_consult.github_api import _get
from oss_consult.output import _UNTRUSTED_NOTICE, _api_fail, _no_pat, _out

_REPO_PAGES = 10
_DEFAULT_LIMIT = 100


def cmd_list_repos(args) -> int:
    pat = github_api._pat(args.owner, None)
    if not pat:
        return _no_pat()
    limit = getattr(args, "limit", _DEFAULT_LIMIT)
    include_other = getattr(args, "include_other_owners", False)
    rows: list[dict] = []
    pages_capped = False
    try:
        if args.owner:
            kind = _get(f"/users/{args.owner}", pat).get("type")
            base = f"/orgs/{args.owner}/repos" if kind == "Organization" else f"/users/{args.owner}/repos"
            query = "type=all"
        else:
            base, query = "/user/repos", "affiliation=owner,organization_member"
        for page in range(1, _REPO_PAGES + 1):
            items = _get(f"{base}?per_page=100&page={page}&{query}", pat)
            for r in items:
                rows.append({
                    "repo": r["full_name"],
                    "owner": (r.get("owner") or {}).get("login") or r["full_name"].split("/")[0],
                    "private": r["private"], "fork": r["fork"],
                    "archived": r["archived"], "stars": r["stargazers_count"],
                    "language": r.get("language"), "created_at": r.get("created_at"),
                    "pushed_at": r.get("pushed_at"),
                    "has_description": bool(r.get("description")),
                    "license_spdx": (r.get("license") or {}).get("spdx_id"),
                })
            if len(items) < 100:
                break
        else:
            # 모든 페이지가 가득 찼다 → 상한 때문에 더 있을 수 있다
            pages_capped = True
    except (gh_client.GitHubAPIError, gh_client.GitHubNetworkError) as e:
        return _api_fail(e, pat)
    if not args.include_all:
        rows = [r for r in rows if not (r["private"] or r["fork"] or r["archived"])]
    other_owners: list[str] = []
    other_count = 0
    if args.owner:
        # /users/X/repos?type=all 은 X 가 멤버인 타 조직 레포를 섞어 준다 — 기본은 X 소유만 남긴다
        mine = [r for r in rows if r["owner"].lower() == args.owner.lower()]
        others = [r for r in rows if r["owner"].lower() != args.owner.lower()]
        other_count = len(others)
        other_owners = sorted({r["owner"] for r in others})
        rows = rows if include_other else mine
    rows.sort(key=lambda r: r["stars"], reverse=True)
    total = len(rows)
    capped = pages_capped
    if limit and total > limit:
        rows = rows[:limit]
        capped = True
    by_owner = dict(Counter(r["owner"] for r in rows))
    note = []
    if capped:
        note.append(f"상한으로 잘림(전체 {total}개 중 {len(rows)}개; --limit 0 이면 전체)")
    if other_count and not include_other:
        note.append(f"타 소유자 레포 {other_count}개 제외({', '.join(other_owners)}; --include-other-owners 로 포함)")
    return _out({"data": {"count": len(rows), "total_before_limit": total, "limit": limit, "capped": capped,
                          "pages_capped": pages_capped, "by_owner": by_owner,
                          "other_owner_count": other_count, "other_owners": other_owners, "repos": rows},
                 "summary": f"레포 {len(rows)}개" + ("; " + "; ".join(note) if note else ""),
                 "untrusted": ["data.repos[].repo", "data.repos[].language"],
                 "untrusted_notice": _UNTRUSTED_NOTICE,
                 "next": "대상마다 collect OWNER/REPO 를 부른다 (레포당 API 약 10회 — 한 번에 20개 안팎으로 나눈다)"}, pat)
