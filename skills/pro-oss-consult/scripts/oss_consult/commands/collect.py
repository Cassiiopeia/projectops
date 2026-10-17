"""collect: 원격 레포 하나의 오픈소스 준비 사실 수집 (메타 > 목록 > 라벨·README·릴리스·이슈 > 건강 파일)
"""
from __future__ import annotations

from common import gh_client

from oss_consult import github_api
from oss_consult.github_api import _file_text, _get, _label_records, _listing, _readme, classify_api_error
from oss_consult.output import (_COLLECT_UNTRUSTED, _UNTRUSTED_NOTICE, _api_fail, _bad_slug, _no_pat, _out,
                                _split)
from oss_consult.readme_facts import (TOP_LINES, analyze_readme, detect_files, extra_privacy_dirs,
                                      summarize_labels, text_head)


def cmd_collect(args) -> int:
    target = _split(args.target)
    if not target:
        return _bad_slug()
    owner, repo = target
    pat = github_api._pat(owner, repo)
    if not pat:
        return _no_pat()
    top_lines = getattr(args, "readme_lines", TOP_LINES)
    errors: list[dict] = []

    def opt(name: str, fn, default):
        """선택 엔드포인트 — 실패해도 나머지 사실은 계속 모은다. 실패는 errors 로 알린다."""
        try:
            return fn()
        except (gh_client.GitHubAPIError, gh_client.GitHubNetworkError) as e:
            errors.append({"endpoint": name, "code": classify_api_error(e)["code"]})
            return default

    try:
        meta = _get(f"/repos/{owner}/{repo}", pat)
    except (gh_client.GitHubAPIError, gh_client.GitHubNetworkError) as e:
        return _api_fail(e, pat)

    root = opt("root", lambda: _listing(owner, repo, "", pat), {})
    gh = opt("github_dir", lambda: _listing(owner, repo, ".github", pat), {})
    docs = opt("docs_dir", lambda: _listing(owner, repo, "docs", pat), {})
    templates = list(opt("issue_templates", lambda: _listing(owner, repo, ".github/ISSUE_TEMPLATE", pat), {}))
    workflows = [n for n in opt("workflows", lambda: _listing(owner, repo, ".github/workflows", pat), {})
                 if n.endswith((".yml", ".yaml"))]
    extra = {sub: opt(f"listing:{sub}", lambda s=sub: _listing(owner, repo, s, pat), {})
             for sub in extra_privacy_dirs(root, docs)}
    label_rows, labels_capped = opt("labels", lambda: _label_records(owner, repo, pat), ([], False))
    readme = opt("readme", lambda: _readme(owner, repo, pat), None)
    releases = opt("releases", lambda: _get(f"/repos/{owner}/{repo}/releases?per_page=10", pat), [])
    tags = opt("tags", lambda: _get(f"/repos/{owner}/{repo}/tags?per_page=30", pat), []) if not releases else []
    issues = opt("issues", lambda: _get(f"/repos/{owner}/{repo}/issues?state=all&per_page=30", pat), [])

    files = detect_files(root, gh, docs, templates, extra)
    # 앞부분만 사실로 싣는다 — 빈 문서 여부는 에이전트가 원문을 보고 판단
    for key in ("contributing", "security"):
        hit = files.get(key)
        if hit and hit["type"] == "file":
            path = {"root": hit["name"], ".github": f".github/{hit['name']}", "docs": f"docs/{hit['name']}"}[hit["where"]]
            txt = opt(f"{key}_text", lambda p=path: _file_text(owner, repo, p, pat), None)
            if txt is not None:
                hit.update(text_head(txt))

    lic = meta.get("license") or {}
    latest = releases[0] if releases else {}
    stable = next((r for r in releases if not r.get("prerelease") and not r.get("draft")), None)
    truncated = {}
    root_entries = sorted(root)
    if len(root_entries) > 80:
        truncated["root_entries"] = {"total": len(root_entries), "shown": 80}
    labels = summarize_labels([it["name"] for it in label_rows], labels_capped)
    if labels["truncated"]:
        truncated["labels.names"] = {"total": labels["count"], "shown": 150}
    rd = analyze_readme(readme, top_lines)
    for k in ("headings", "media"):
        if rd.get(f"{k}_truncated"):
            truncated[f"readme.{k}"] = {"total": rd[f"{k}_total"], "shown": len(rd[k])}
    if labels_capped:
        truncated["labels.capped"] = {"total": ">=500", "shown": labels["count"]}

    sample = issues[:20]
    data = {
        "repo": f"{owner}/{repo}",
        "meta": {
            "description": meta.get("description"),
            "homepage": meta.get("homepage") or None,
            "topics": meta.get("topics", []),
            "language": meta.get("language"),
            "license_spdx": lic.get("spdx_id"),
            "stars": meta.get("stargazers_count", 0),
            "forks": meta.get("forks_count", 0),
            "open_issues": meta.get("open_issues_count", 0),
            "open_issues_count": meta.get("open_issues_count", 0),
            "created_at": meta.get("created_at"),
            "pushed_at": meta.get("pushed_at"),
            "archived": meta.get("archived", False),
            "fork": meta.get("fork", False),
            "is_template": meta.get("is_template", False),
            "private": meta.get("private", False),
            "has_discussions": meta.get("has_discussions", False),
            "has_pages": meta.get("has_pages", False),
            "has_wiki": meta.get("has_wiki", False),
            "default_branch": meta.get("default_branch"),
        },
        "files": files,
        "root_entries": root_entries[:80],
        "workflows": len(workflows),
        "labels": labels,
        "readme": rd,
        "releases": {
            "recent": len(releases),
            "latest": latest.get("tag_name") if latest else None,
            "latest_at": latest.get("published_at") if latest else None,
            "latest_prerelease": bool(latest.get("prerelease")) if latest else None,
            "latest_draft": bool(latest.get("draft")) if latest else None,
            "latest_stable": stable.get("tag_name") if stable else None,
            "assets_on_latest": len(latest.get("assets", [])) if latest else 0,
            # 릴리스 없이 태그만 쓰는 레포를 "배포 없음"으로 오해하지 않게.
            # 릴리스가 있으면 태그를 조회하지 않는다 — 0 으로 두면 "태그 없음"으로 읽혀서 null 로 구분한다
            "tags_checked": not releases,
            "tags_count": len(tags) if not releases else None,
            "tags_capped": len(tags) >= 30 if not releases else None,
        },
        # 이슈 관리 방식·외부 PR 응대는 제목·날짜·작성자 관계를 보고 에이전트가 읽는다 (PR 도 섞여 온다)
        "issues_sample": [
            {"number": i.get("number"), "title": i.get("title", "")[:120], "state": i.get("state"),
             "is_pr": "pull_request" in i,
             "created_at": i.get("created_at"), "updated_at": i.get("updated_at"),
             "labels": [lb["name"] for lb in i.get("labels", [])],
             "author": (i.get("user") or {}).get("login"),
             "author_association": i.get("author_association"),
             "comments": i.get("comments", 0)}
            for i in sample
        ],
        "truncated": truncated,
        "errors": errors,
    }
    notes = []
    if errors:
        notes.append(f"일부 실패 {len(errors)}건({', '.join(e['endpoint'] for e in errors)}) — 해당 사실은 '미확인'으로 다룬다")
    if truncated:
        notes.append(f"일부 절단({', '.join(truncated)})")
    return _out({"data": data,
                 "code": "partial" if errors else "ok",
                 "summary": f"{owner}/{repo} 사실 수집 완료" + ("; " + "; ".join(notes) if notes else ""),
                 "untrusted": _COLLECT_UNTRUSTED, "untrusted_notice": _UNTRUSTED_NOTICE,
                 "next": "references/rubric.md 로 성격 판별과 축별 채점을 한다"}, pat)
