"""Onboarding facts: capture mode recommendation, where the agent rule can live (CLAUDE.md tracked or ignored), rule block
The block text comes from i18n/<language>.json so every repo gets the same wording; markers make updates idempotent.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from .repo_facts import GitError, path_tracking_state, run_git

BLOCK_BEGIN = "<!-- pro-brain:begin (managed by /pro-brain; settings live in version.yml) -->"
BLOCK_END = "<!-- pro-brain:end -->"
BLOCK_PATTERN = re.compile(r"<!-- pro-brain:begin[^>]*-->.*?<!-- pro-brain:end -->", re.DOTALL)
# Claude Code loads .claude/rules/*.md without paths frontmatter at launch, like .claude/CLAUDE.md
RULES_FILE = ".claude/rules/pro-brain.md"
CLAUDE_MD_CANDIDATES = ("CLAUDE.md", ".claude/CLAUDE.md")
HISTORY_SCAN_LIMIT = 300        # default-branch commits read for the capture recommendation
ISSUE_SIGNAL_MINIMUM = 3        # issue links or issue branches needed to recommend issue-end
PR_SIGNAL_MINIMUM = 3           # PR merges needed to recommend merge
ISSUE_BRANCH = re.compile(r"^(?:origin/)?\d{8}_#\d+_")
I18N_FOLDER = Path(__file__).resolve().parent / "i18n"
# Root files that usually hold a repo's own vault rules (note types, ids, folders); first match is proposed as `rules`
RULES_CANDIDATES = ("SECOND-BRAIN.md", "KNOWLEDGE.md", "VAULT.md")


def detect_rules_file(repo_root: Path) -> str | None:
    return next((name for name in RULES_CANDIDATES if (repo_root / name).is_file()), None)


def load_strings(language: str) -> dict:
    path = I18N_FOLDER / f"{language}.json"
    return json.loads((path if path.is_file() else I18N_FOLDER / "en.json").read_text(encoding="utf-8"))


def render_block(language: str, capture: str, knowledge_path: str, default_branch: str, brain_mcp: str | None,
                 rules_file: str | None = None) -> str:
    """Rule block for the project agent instructions, in the repo's language"""
    strings = load_strings(language)
    values = {"path": knowledge_path, "default_branch": default_branch, "brain_mcp": brain_mcp or "", "rules": rules_file or ""}
    sync = strings["sync_suffix"].format(**values) if brain_mcp else ""
    lookup = strings["lookup_with_brain" if brain_mcp else "lookup_without_brain"].format(**values)
    lines = [
        BLOCK_BEGIN,
        strings["heading"],
        "",
        strings["intro"].format(sync=sync, **values) + (strings["rules_ref"].format(**values) if rules_file else ""),
        "",
        f"- **{strings['when_label']}**: {strings['mode_' + capture].format(**values)}",
        f"- **{strings['lookup_label']}**: {lookup}",
        f"- {strings['rules']}",
        f"- {strings['settings']}",
        BLOCK_END,
    ]
    return "\n".join(lines)


def recommend_capture(repo_root: Path, ref: str, remote_slug: str | None) -> dict:
    """issue-end when the repo works in issues, merge when it merges PRs, else session-end; reasons listed"""
    try:
        subjects_and_bodies = run_git(repo_root, "log", f"-n{HISTORY_SCAN_LIMIT}", "--format=%s%n%b%x1e", ref)
    except GitError:
        subjects_and_bodies = ""
    records = [record for record in subjects_and_bodies.split("\x1e") if record.strip()]
    slug_pattern = re.escape(remote_slug) if remote_slug else r"[^/\s]+/[^/\s]+"
    issue_links = sum(1 for record in records if re.search(rf"github\.com/{slug_pattern}/issues/\d+", record, re.IGNORECASE)
                      or re.search(r"\d{8}_#\d+_", record))
    pr_merges = sum(1 for record in records if record.startswith("Merge pull request #"))
    try:
        branch_names = run_git(repo_root, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes").split()
    except GitError:
        branch_names = []
    issue_branches = sum(1 for name in branch_names if ISSUE_BRANCH.match(name))
    has_issue_templates = (repo_root / ".github" / "ISSUE_TEMPLATE").is_dir()
    signals = {"commits_scanned": len(records), "commits_linking_issues": issue_links, "issue_branches": issue_branches,
               "pr_merges": pr_merges, "has_issue_templates": has_issue_templates}
    if issue_links >= ISSUE_SIGNAL_MINIMUM or issue_branches >= ISSUE_SIGNAL_MINIMUM:
        reason = (f"{issue_links} of the last {len(records)} commits link an issue and {issue_branches} branch(es) are "
                  "named YYYYMMDD_#N_title: the repo works in issues, so one note per finished issue fits")
        return {"mode": "issue-end", "reason": reason, "signals": signals}
    if pr_merges >= PR_SIGNAL_MINIMUM:
        reason = f"{pr_merges} PR merges but few issue links: one note per merged change set fits"
        return {"mode": "merge", "reason": reason, "signals": signals}
    reason = "no issue or PR flow in recent history: capture at the end of a work session or after a feature commit"
    return {"mode": "session-end", "reason": reason, "signals": signals}


def block_state(file_path: Path, expected_block: str) -> str:
    """current | outdated | absent (absent also when the file does not exist)"""
    if not file_path.is_file():
        return "absent"
    match = BLOCK_PATTERN.search(file_path.read_text(encoding="utf-8", errors="replace"))
    if not match:
        return "absent"
    return "current" if match.group(0).strip() == expected_block.strip() else "outdated"


def instruction_files(repo_root: Path) -> dict:
    """Project CLAUDE.md (root or .claude/), the rules file and AGENTS.md with their git tracking state"""
    primary = next((name for name in CLAUDE_MD_CANDIDATES if (repo_root / name).is_file()), None)
    agents_tracked = path_tracking_state(repo_root, "AGENTS.md") == "tracked"
    agents_text = (repo_root / "AGENTS.md").read_text(encoding="utf-8", errors="replace") if agents_tracked else ""
    return {
        "claude_md": primary,
        "claude_md_state": path_tracking_state(repo_root, primary or "CLAUDE.md"),
        "rules_file": RULES_FILE,
        "rules_file_state": path_tracking_state(repo_root, RULES_FILE),
        # Codex and other agents read AGENTS.md; worth the same block unless it already imports CLAUDE.md
        "agents_md_needs_block": agents_tracked and "@CLAUDE.md" not in agents_text,
    }


def target_options(files: dict) -> list[dict]:
    """Where the block can go, recommended first, with the reason shown to the user"""
    claude_md, state, rules_state = files["claude_md"], files["claude_md_state"], files["rules_file_state"]
    rules_option = {"target": RULES_FILE, "kind": "tracked-rules-file",
                    "why": "tracked, so every clone and worktree gets it; Claude Code loads .claude/rules/*.md at launch "
                           "the same way as .claude/CLAUDE.md"}
    copy_option = {"target": claude_md or "CLAUDE.md", "kind": "local-claude-md+worktree-copy",
                   "why": "stays local and untracked; registered in the pro-init-worktree copy set so new worktrees on "
                          "this machine get it (teammates and fresh clones do not)"}
    if claude_md and state == "tracked":
        return [{"target": claude_md, "kind": "tracked-claude-md", "recommended": True,
                 "why": "already tracked, so every clone and worktree gets the block"}]
    if claude_md is None:
        # A new CLAUDE.md would stop Claude Code from reading AGENTS.md, so a rules file is the safe default
        options = [rules_option, {"target": "CLAUDE.md", "kind": "new-claude-md",
                                  "why": "creates CLAUDE.md; Claude Code then stops falling back to AGENTS.md"}]
    elif rules_state != "ignored":
        options = [rules_option, copy_option]
    else:
        options = [copy_option]
    if state == "untracked":
        options.append({"target": claude_md, "kind": "commit-claude-md",
                        "why": "CLAUDE.md is neither tracked nor ignored: committing it shares the whole file"})
    options[0]["recommended"] = True
    return options


def apply_block(file_path: Path, block: str) -> str:
    """Write the block between markers: created | updated | appended | unchanged"""
    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(block + "\n", encoding="utf-8")
        return "created"
    text = file_path.read_text(encoding="utf-8", errors="replace")
    match = BLOCK_PATTERN.search(text)
    if match:
        if match.group(0).strip() == block.strip():
            return "unchanged"
        file_path.write_text(text[:match.start()] + block + text[match.end():], encoding="utf-8")
        return "updated"
    separator = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    file_path.write_text(text + separator + block + "\n", encoding="utf-8")
    return "appended"


def preview_diff(file_path: Path, relative: str, block: str) -> str:
    """Unified diff of what apply_block would change (nothing is written)"""
    before = file_path.read_text(encoding="utf-8", errors="replace") if file_path.is_file() else ""
    match = BLOCK_PATTERN.search(before)
    if match:
        after = before[:match.start()] + block + before[match.end():]
    elif before:
        after = before + ("" if before.endswith("\n\n") else ("\n" if before.endswith("\n") else "\n\n")) + block + "\n"
    else:
        after = block + "\n"
    return "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                        fromfile=f"a/{relative}", tofile=f"b/{relative}", n=1))
