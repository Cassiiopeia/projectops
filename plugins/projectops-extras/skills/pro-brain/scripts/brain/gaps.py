"""Gap check: work merged into the default branch since the last captured note that has no note yet
git and the note files only (no network, no LLM), so a brain sync script can run it every hour for free.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import notes
from .repo_facts import GitError, run_git

GAP_LIMIT = 50                   # items listed; the count is always exact
UNLINKED_SAMPLE_LIMIT = 5        # sample subjects of commits that link no issue (issue-end mode)
FALLBACK_WINDOW = "30 days ago"  # window when no note was ever committed
RECORD_SEPARATOR, FIELD_SEPARATOR = "\x1e", "\x1f"

SKIP_CI = re.compile(r"\[skip ci\]", re.IGNORECASE)
# Merges that only sync long-lived branches carry no work of their own
SYNC_MERGE = re.compile(r"^Merge (?:remote-tracking )?branch '(?:origin/)?(?:main|master|develop|dev|deploy)'"
                        r"(?: of [^ ]+)?(?: into [\w/.-]+)?$", re.IGNORECASE)
PR_MERGE = re.compile(r"^Merge pull request #(\d+) from (\S+)")
BRANCH_MERGE = re.compile(r"^Merge branch '([^']+)'")
SQUASH_PR = re.compile(r"\(#(\d+)\)\s*$")
BRANCH_ISSUE = re.compile(r"#(\d+)")
DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def commit_type(subject: str) -> str | None:
    """'title : fix : body' (projectops) or 'fix(scope)!: body' (conventional) > fix"""
    parts = [part.strip() for part in subject.split(" : ")]
    if len(parts) >= 3 and re.fullmatch(r"[a-z]+!?", parts[1]):
        return parts[1].rstrip("!")
    match = re.match(r"^([a-z]+)(?:\([^)]*\))?!?:\s", subject)
    return match.group(1) if match else None


def _log(repo_root: Path, ref: str, window: dict, first_parent: bool) -> list[dict]:
    arguments = ["log", "--format=%H%x1f%P%x1f%s%x1f%b%x1f%cI%x1e"]
    if first_parent:
        arguments.append("--first-parent")
    arguments += [f"--since={window['since']}", ref] if window.get("since") else [f"{window['boundary']}..{ref}"]
    commits = []
    for record in run_git(repo_root, *arguments).split(RECORD_SEPARATOR):
        fields = record.strip("\n").split(FIELD_SEPARATOR)
        if len(fields) < 5:
            continue
        sha, parents, subject, body, date = fields[:5]
        commits.append({"sha": sha, "parents": parents.split(), "subject": subject, "body": body, "date": date[:10]})
    return commits


def resolve_window(repo_root: Path, ref: str, knowledge_path: str, since: str | None) -> dict:
    """--since date or ref > last commit on ref that touched the knowledge folder > fallback window"""
    if since:
        if DATE_ONLY.match(since):
            return {"since": since, "from": f"date {since}"}
        boundary = run_git(repo_root, "rev-parse", "--verify", f"{since}^{{commit}}").strip()
        return {"boundary": boundary, "from": f"ref {since}"}
    try:
        last = run_git(repo_root, "log", "-1", "--format=%H", ref, "--", knowledge_path).strip()
    except GitError:
        last = ""
    if last:
        return {"boundary": last, "from": f"last note commit {last[:9]}"}
    return {"since": FALLBACK_WINDOW, "from": f"no note commit yet, last {FALLBACK_WINDOW.replace(' ago', '')}"}


def _is_skipped(subjects: list[str], skip: list[str]) -> bool:
    """True when every subject's commit type (or a skip word in it) is on the repo's skip list"""
    if not skip or not subjects:
        return False
    lowered = [word.lower() for word in skip]
    return all((commit_type(subject) or "") in lowered or any(word in subject.lower() for word in lowered if len(word) > 3)
               for subject in subjects)


def issue_gaps(commits: list[dict], remote_slug: str | None, covered_issues: set[int], skip: list[str]) -> dict:
    """issue-end: issues referenced by merged commits (issue URLs, issue branch names) that no note mentions"""
    slug_pattern = re.escape(remote_slug) if remote_slug else r"[^/\s]+/[^/\s]+"
    by_issue: dict[int, dict] = {}
    unlinked = []
    for commit in commits:
        if SKIP_CI.search(commit["subject"]) or SYNC_MERGE.match(commit["subject"]):
            continue
        message = commit["subject"] + "\n" + commit["body"]
        numbers = {int(number) for number in re.findall(rf"github\.com/{slug_pattern}/issues/(\d+)", message, re.IGNORECASE)}
        merge = PR_MERGE.match(commit["subject"]) or BRANCH_MERGE.match(commit["subject"])
        if merge:
            numbers |= {int(number) for number in BRANCH_ISSUE.findall(merge.group(merge.lastindex))}
        if not numbers:
            if len(commit["parents"]) < 2:
                unlinked.append(commit["subject"][:120])
            continue
        for number in numbers:
            entry = by_issue.setdefault(number, {"issue": number, "commits": 0, "last_date": "", "subjects": []})
            if merge and "branch" not in entry:
                entry["branch"] = merge.group(merge.lastindex)
            entry["commits"] += 1
            entry["last_date"] = max(entry["last_date"], commit["date"])
            if not merge and len(entry["subjects"]) < 2:
                entry["subjects"].append(commit["subject"][:120])
    gaps, skipped = [], 0
    for number in sorted(by_issue, reverse=True):
        if number in covered_issues:
            continue
        entry = by_issue[number]
        if _is_skipped(entry["subjects"], skip):
            skipped += 1
            continue
        gaps.append({"kind": "issue", **entry})
    return {"gaps": gaps, "covered": len([n for n in by_issue if n in covered_issues]), "skipped_by_rule": skipped,
            "unlinked_commits": len(unlinked), "unlinked_samples": unlinked[:UNLINKED_SAMPLE_LIMIT]}


def change_gaps(commits: list[dict], covered_pulls: set[int], covered_shas: set[str], mentioned_shas: set[str],
                skip: list[str]) -> dict:
    """session-end / merge / manual: first-parent merges, PRs and direct commits that no note covers"""
    def is_covered(sha: str) -> bool:
        return sha in covered_shas or any(sha.startswith(prefix) for prefix in mentioned_shas)

    gaps, covered, skipped = [], 0, 0
    for commit in commits:
        subject = commit["subject"]
        if SKIP_CI.search(subject) or SYNC_MERGE.match(subject):
            continue
        pull_match = PR_MERGE.match(subject) or SQUASH_PR.search(subject)
        pull = int(pull_match.group(1)) if pull_match else None
        branch_head = commit["parents"][1] if len(commit["parents"]) > 1 else None
        if (pull and pull in covered_pulls) or is_covered(commit["sha"]) or (branch_head and is_covered(branch_head)):
            covered += 1
            continue
        if _is_skipped([subject], skip):
            skipped += 1
            continue
        branch_match = PR_MERGE.match(subject) or BRANCH_MERGE.match(subject)
        item = {"kind": "pr" if pull else ("merge" if branch_head else "commit"), "sha": commit["sha"][:9],
                "date": commit["date"], "subject": subject[:120]}
        if pull:
            item["pr"] = pull
        if branch_match:
            item["branch"] = branch_match.group(branch_match.lastindex)
        gaps.append(item)
    return {"gaps": gaps, "covered": covered, "skipped_by_rule": skipped}


def find_gaps(repo_root: Path, ref: str, knowledge_path: str, capture: str, remote_slug: str | None,
              since: str | None, skip: list[str]) -> dict:
    window = resolve_window(repo_root, ref, knowledge_path, since)
    existing = notes.scan_notes(repo_root / knowledge_path, remote_slug)
    if capture == "issue-end":
        result = issue_gaps(_log(repo_root, ref, window, first_parent=False), remote_slug,
                            set().union(*(note["issues"] for note in existing)) if existing else set(), skip)
    else:
        result = change_gaps(_log(repo_root, ref, window, first_parent=True),
                             set().union(*(note["pulls"] for note in existing)) if existing else set(),
                             notes.covered_commits(repo_root, existing),
                             set().union(*(note["shas"] for note in existing)) if existing else set(), skip)
    total = len(result["gaps"])
    result["gaps"] = result["gaps"][:GAP_LIMIT]
    return {"window": window["from"], "ref": ref, "capture": capture, "note_count": len(existing), "gap_count": total,
            **result}


def format_text(project: str, report: dict) -> str:
    """One log block for sync scripts: a header line, then one line per gap"""
    header = (f"[pro-brain gaps] {project}: {report['gap_count']} item(s) without a note "
              f"(capture {report['capture']}, {report['window']}, ref {report['ref']})")
    lines = [header]
    for gap in report["gaps"]:
        if gap["kind"] == "issue":
            lines.append(f"  issue #{gap['issue']} ({gap['commits']} commit(s), {gap['last_date']}) "
                         f"{(gap['subjects'] or [gap.get('branch', '')])[0]}")
        else:
            label = f"PR #{gap['pr']}" if gap.get("pr") else gap["kind"]
            lines.append(f"  {label} {gap['sha']} {gap['date']} {gap['subject']}")
    return "\n".join(lines)
