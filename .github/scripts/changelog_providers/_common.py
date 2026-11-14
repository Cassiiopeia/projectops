#!/usr/bin/env python3
"""Shared helpers for changelog providers (#455) — stdlib only.

Every provider follows the same contract:
  input: env vars (COMMIT_RANGE, etc.)
  output: on success pr_body.md in cwd (fixed Summary by CodeRabbit structure) + stdout `PROVIDER=<name>` + exit 0
        on failure the reason on stderr + exit 1 (the ladder falls back to the next step)
"""
import os
import re
import subprocess
import sys

# The catalog (#787) is one level above the script folder — set the path so imports work when a provider runs directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from i18n.messages import resolve_language, t  # noqa: E402

HEADER = "<!-- This is an auto-generated comment: release notes by coderabbit.ai -->"
FOOTER = "<!-- end of auto-generated comment: release notes by coderabbit.ai -->"

# Release-notes section order. Display names come from the catalog in the repo language (#793)
SECTION_ORDER = ["feat", "fix", "improve", "docs", "etc"]
# Rules for extracting the type from a commit subject — both conventions are recognized (#566).
#   tier-1: "title : feat : text"     <- projectops standard (type in the middle)
#   tier-2: "feat: text"              <- Conventional Commits
# tier-1 is checked first. The tier-2 regex looks only at line start, so it missed tier-1 entirely,
# and commits following our own convention all fell into "other".
# Uses the same criteria as changelog_manager.classify_bump_level() (#546).
_TYPES = "feat|fix|refactor|docs|chore|style|test|perf|ci|build|revert"
_TIER1_RE = re.compile(rf"^(?P<title>.+?)\s:\s*(?P<type>{_TYPES})!?\s*:\s*(?P<body>.+)$", re.IGNORECASE)
_TIER2_RE = re.compile(rf"^(?P<type>{_TYPES})(?:\([^)]*\))?!?:\s*(?P<body>.+)$", re.IGNORECASE)
_PREFIX_TO_SECTION = {
    "feat": "feat", "fix": "fix",
    "refactor": "improve", "style": "improve", "perf": "improve",
    "docs": "docs",
}


def parse_commit(line):
    """Commit subject -> (section key, text shown to users). No match -> ("etc", original)."""
    m = _TIER1_RE.match(line) or _TIER2_RE.match(line)
    if not m:
        return "etc", _strip_noise(line) or line.strip()
    section = _PREFIX_TO_SECTION.get(m.group("type").lower(), "etc")
    return section, (_strip_noise(m.group("body")) or line.strip())


def _strip_noise(text):
    """Remove issue numbers (#123) and URLs, then tidy spaces — tokens meaningless to users."""
    s = re.sub(r"https?://\S+", "", text)
    s = re.sub(r"#[0-9]+", "", s)
    return re.sub(r" {2,}", " ", s).strip()


# Last-resort default when the release PR base is unknown
DEFAULT_RELEASE_BASE = "main"


def release_commit_range():
    """Release-notes commit range: COMMIT_RANGE > origin/<PR base>..HEAD > origin/main..HEAD (#1114)

    Actions sets GITHUB_BASE_REF on pull_request(_target) events. Keeps the range non-empty in repos whose base is not main.
    """
    explicit = os.environ.get("COMMIT_RANGE", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("GITHUB_BASE_REF", "").strip() or DEFAULT_RELEASE_BASE
    return f"origin/{base}..HEAD"


def collect_commits(range_expr, limit=60, fallback_count=30):
    """Collect commit subjects in the range ([skip ci] excluded). Empty -> fall back to recent commits."""
    def _log(args):
        try:
            out = subprocess.run(
                ["git", "log", *args, "--pretty=format:%s"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if out.returncode != 0:
                return []
            return [s for s in out.stdout.splitlines() if s.strip() and "[skip ci]" not in s
                    and not s.strip().startswith("Merge ")]  # same criteria as the bump decision (#686)
        except OSError:
            return []

    commits = _log([range_expr])[:limit]
    if not commits:
        commits = _log([f"-{fallback_count}"])
    return commits


def clean_message(line):
    """Return only the body of a commit subject with type prefix, issue numbers and URLs removed."""
    return parse_commit(line)[1]


def classify(commits):
    """Group commit subjects by section: {section key: [messages...]}."""
    sections = {key: [] for key in SECTION_ORDER}
    for line in commits:
        key, message = parse_commit(line)
        sections[key].append(message)
    return sections


def sections_to_markdown(sections, lang=None):
    lang = lang or resolve_language()
    parts = []
    for key in SECTION_ORDER:
        title = t(f"release_notes.section.{key}", lang)
        items = sections.get(key) or []
        if not items:
            continue
        parts.append(f"* **{title}**")
        parts.extend(f"  * {msg}" for msg in items)
        parts.append("")
    return "\n".join(parts).rstrip("\n")


def empty_notes(lang=None):
    """Fallback body when no commits were collected."""
    lang = lang or resolve_language()
    return f"* **{t('release_notes.section.etc', lang)}**\n  * {t('release_notes.empty', lang)}"


def write_pr_body(content, path="pr_body.md", lang=None):
    """Wrap in the fixed Summary by CodeRabbit structure and save pr_body.md — the changelog_manager.py parsing contract.

    The `Summary by CodeRabbit` line is a contract the workflow reads, so it is not translated. Only the headings below follow the language.
    """
    lang = lang or resolve_language()
    body = "\n".join([
        HEADER, "",
        "## Summary by CodeRabbit", "",
        f"## {t('release_notes.heading', lang)}", "",
        content, "",
        FOOTER, "",
    ])
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


def fail(reason):
    print(reason, file=sys.stderr)
    sys.exit(1)
