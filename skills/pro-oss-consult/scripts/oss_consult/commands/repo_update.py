"""repo-update: change repo About, topics and Discussions (read before > plan and validate > plan only on --dry-run > apply > verify after)
Call only after approval. Not implemented: visibility changes, repo delete/rename/archive, default branch changes
"""
from __future__ import annotations

import re

from common import gh_client

from oss_consult import github_api
from oss_consult.github_api import _get
from oss_consult.output import _api_fail, _bad_slug, _fail, _no_pat, _out, _split

# Per the official docs: topics are lowercase letters, digits and hyphens, 50 chars max, 20 per repo max
# (docs.github.com/.../classifying-your-repository-with-topics). The 350-char About limit was only found via search — needs confirming.
_TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
MAX_TOPICS = 20
MAX_DESCRIPTION = 350


def _write_repo_state(owner: str, repo: str, pat: str) -> dict:
    meta = _get(f"/repos/{owner}/{repo}", pat)
    topics = _get(f"/repos/{owner}/{repo}/topics", pat).get("names", meta.get("topics", []))
    return {"description": meta.get("description"), "homepage": meta.get("homepage") or None,
            "topics": topics, "has_discussions": meta.get("has_discussions", False)}


def plan_repo_update(before: dict, args) -> tuple[dict, str | None]:
    """Return only the values to change as a plan. On validation failure (empty plan, error message)."""
    plan: dict = {}
    if args.description is not None:
        if not args.description.strip():
            return {}, "Clearing description is not supported (destructive changes are only proposed)"
        if len(args.description) > MAX_DESCRIPTION:
            return {}, f"description must be {MAX_DESCRIPTION} characters or fewer (currently {len(args.description)})"
        if args.description != (before["description"] or ""):
            plan["description"] = args.description
    if args.homepage is not None:
        if not re.match(r"^https?://\S+$", args.homepage):
            return {}, "homepage must be an http(s):// URL (clearing the value is not supported)"
        if args.homepage != (before["homepage"] or ""):
            plan["homepage"] = args.homepage
    if args.topics is not None:
        new = [t.strip().lower() for t in args.topics.split(",") if t.strip()]
        if not new and args.topics_mode == "replace":
            return {}, "Replacing topics with an empty list is not supported (destructive changes are only proposed)"
        bad = [t for t in new if not _TOPIC_RE.match(t)]
        if bad:
            return {}, f"Topics must be lowercase letters, digits and hyphens, 50 characters or fewer: {', '.join(bad)}"
        merged = list(dict.fromkeys(new if args.topics_mode == "replace" else before["topics"] + new))
        if len(merged) > MAX_TOPICS:
            return {}, f"A repo can have at most {MAX_TOPICS} topics (planned {len(merged)})"
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
        return _fail("nothing_to_change", "Nothing to change",
                     "Pass at least one of --description, --homepage, --topics, --discussions")
    pat = github_api._pat(owner, repo)
    if not pat:
        return _no_pat()
    try:
        before = _write_repo_state(owner, repo, pat)
    except (gh_client.GitHubAPIError, gh_client.GitHubNetworkError) as e:
        return _api_fail(e, pat)
    plan, err = plan_repo_update(before, args)
    if err:
        return _fail("invalid_input", err, "Fix the input and run again", pat, before=before)
    if not plan:
        return _out({"code": "no_change", "data": {"repo": f"{owner}/{repo}", "before": before, "planned": {}},
                     "summary": "Already in the wanted state — nothing to change", "next": "Move on to the next action"}, pat)
    if args.dry_run:
        return _out({"data": {"repo": f"{owner}/{repo}", "dry_run": True, "before": before, "planned": plan},
                     "summary": "Plan only (--dry-run). Nothing was applied",
                     "next": "After the user approves, run the same command without --dry-run"}, pat)
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
        # It may be partly applied — report it so it can be rolled back with before
        return _api_fail(e, pat, before=before, applied=applied)
    try:
        after = _write_repo_state(owner, repo, pat)
    except (gh_client.GitHubAPIError, gh_client.GitHubNetworkError) as e:
        return _api_fail(e, pat, before=before, applied=applied)
    # has_discussions was not confirmed in the official PATCH docs (needs confirming) — re-read to verify it took effect
    warnings = [f"{k} is still {after.get(k)!r} after applying — the API may not apply this field"
                for k in plan if k != "topics" and after.get(k) != plan[k]
                and not (k in ("description", "homepage") and (after.get(k) or "") == plan[k])]
    return _out({"data": {"repo": f"{owner}/{repo}", "dry_run": False, "before": before, "planned": plan,
                          "after": after, "warnings": warnings},
                 "summary": f"Applied: {', '.join(applied)}" + (" — warning: some changes did not take effect" if warnings else ""),
                 "next": "Call collect again to confirm the change. To undo, run repo-update again with the before values"}, pat)
