"""collect: gather one remote repo's open-source readiness facts (meta > listings > labels·README·releases·issues > health files)
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
        """Optional endpoint — on failure the other facts are still collected. Failures are reported in errors."""
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
    # Only the opening part is included as fact — whether the doc is empty is for the agent to judge from the source
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
            # So a repo that uses tags without releases is not mistaken for "no releases".
            # With releases, tags are not queried — 0 would read as "no tags", so null tells them apart
            "tags_checked": not releases,
            "tags_count": len(tags) if not releases else None,
            "tags_capped": len(tags) >= 30 if not releases else None,
        },
        # The agent reads issue handling and responses to outside PRs from titles, dates and author relations (PRs are mixed in)
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
        notes.append(f"{len(errors)} partial failure(s) ({', '.join(e['endpoint'] for e in errors)}) — treat those facts as 'unverified'")
    if truncated:
        notes.append(f"partly truncated ({', '.join(truncated)})")
    return _out({"data": data,
                 "code": "partial" if errors else "ok",
                 "summary": f"Collected facts for {owner}/{repo}" + ("; " + "; ".join(notes) if notes else ""),
                 "untrusted": _COLLECT_UNTRUSTED, "untrusted_notice": _UNTRUSTED_NOTICE,
                 "next": "Use references/rubric.md to detect the repo type and score each axis"}, pat)
