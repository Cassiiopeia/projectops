"""Branch name calculation — Python port of the SUH-ISSUE-HELPER TypeScript logic."""

from __future__ import annotations

import re
from datetime import date


# Keep Unicode letters and digits (including Hangul, kana, CJK and accented Latin); replace the rest with _.
# ⚠️ The source of truth is _KEEP in `.github/scripts/issue_helper.py` (#717). It ships on a different path
# and cannot be imported, so the same rule is duplicated; test_branch_name_parity.py keeps them in sync.
_KEEP_PATTERN = re.compile(r"[^\w]")

# Collapse consecutive underscores into one
_MULTI_UNDERSCORE = re.compile(r"_+")

# Max Git branch length (GitHub reference limit)
_MAX_BRANCH_LEN = 100

# Title tag → commit type.
#
# ⚠️ The source of truth is DEFAULT_COMMIT_TYPE_MAP in `.github/scripts/issue_helper.py`.
# Different ship paths (workflow vs skill) prevent importing it, so the values are kept in sync.
# If they drift, **the commit type the issue comment suggests differs from the one the skill makes.**
# A test enforces the sync (test_commit_template.py).
COMMIT_TYPE_MAP = {
    "버그": "fix",
    "기능요청": "feat",
    "기능추가": "feat",
    "기능개선": "feat",
    "문서": "docs",
    "디자인": "design",
    "시험요청": "test",
    "Bug": "fix",
    "Feature Request": "feat",
    "Feature": "feat",
    "Improvement": "feat",
    "Docs": "docs",
    "Design": "design",
    "QA": "test",
}

# Leading emoji on titles. Variation selectors (U+FE0F) and ZWJ joins are stripped too.
_LEADING_EMOJI = re.compile(
    r"^[🀀-🫿←-⯿ -⁯︀-️‍\s]+"
)

# Consecutive [tags] at the **start** of the title. Brackets in the middle are left alone
# (a title like `.env[테스트] 처리` must not break).
_LEADING_TAGS = re.compile(r"^(?:\[[^\]]*\]\s*)+")

# When the type cannot be determined. Same default as issue_helper.
_FALLBACK_COMMIT_TYPE = "feat"

# Extract [tags] from the title
_TAG_PATTERN = re.compile(r"\[([^\]]*)\]")


def strip_issue_decorations(title: str) -> str:
    """Strip leading emoji and [tags] from an issue title.

    This repo's rule is no emoji or tags in commit messages,
    and leaving that to the agent's memory means it will be missed.

    Args:
        title: original issue title

    Returns:
        The title without decorations. If stripping leaves an empty string, return the original
        (losing the whole title is worse).
    """
    # Emoji and tags can alternate (📄[Docs]🚀[Improvement]), so repeat until nothing changes (#982)
    stripped = title
    while True:
        next_stripped = _LEADING_TAGS.sub("", _LEADING_EMOJI.sub("", stripped))
        if next_stripped == stripped:
            break
        stripped = next_stripped
    stripped = stripped.strip()
    return stripped or title.strip()


# Commit types that can be set directly. Title tag map values + common convention types.
# A trailing `!` marks a breaking change (major), so it is allowed too.
VALID_COMMIT_TYPES = frozenset(set(COMMIT_TYPE_MAP.values()) | {
    "feat", "fix", "docs", "chore", "refactor", "test", "design", "style", "perf", "build", "ci", "revert",
})


def commit_type_arg(value: str) -> str:
    """argparse type validating `--type`. Keeps unknown types out of commit messages (#713)."""
    import argparse
    base = value[:-1] if value.endswith("!") else value
    if base not in VALID_COMMIT_TYPES:
        raise argparse.ArgumentTypeError(
            f"unknown commit type: {value!r} (allowed: {', '.join(sorted(VALID_COMMIT_TYPES))})")
    return value


def date_arg(value: str) -> str:
    """argparse type checking that `--date` is a real YYYYMMDD date (#713)."""
    import argparse
    from datetime import datetime
    try:
        if not re.fullmatch(r"\d{8}", value):
            raise ValueError
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a real date in YYYYMMDD form: {value!r}")
    return value


def infer_commit_type(issue_title: str, type_map: dict | None = None) -> str:
    """Pick the commit type from the title [tag] — fix for bug issues, feat for features.

    In repos with `semver_auto` on, this value decides the release bump size.
    Always passing feat would make even a typo fix a minor release.
    """
    merged = dict(COMMIT_TYPE_MAP)
    if type_map:
        merged.update(type_map)
    lowered = {k.lower(): v for k, v in merged.items()}  # English tags ignore case (#769)
    for tag in _TAG_PATTERN.findall(issue_title):
        key = tag.strip()
        commit_type = merged.get(key) or lowered.get(key.lower())
        if commit_type:
            return commit_type
    return _FALLBACK_COMMIT_TYPE


def normalize_title(title: str) -> str:
    """Normalize an issue title into a branch-name string.

    Args:
        title: title string to normalize

    Returns:
        normalized string (letters incl. Hangul, digits and underscores only)
    """
    # Replace anything other than letters (incl. Hangul) and digits with underscores
    normalized = _KEEP_PATTERN.sub("_", title)

    # Collapse consecutive underscores into one
    normalized = _MULTI_UNDERSCORE.sub("_", normalized)

    # Strip underscores at both ends
    return normalized.strip("_")


def create_branch_name(
    issue_title: str,
    issue_number: int,
    date_yyyymmdd: str | None = None,
) -> str:
    """Build a branch name in the form YYYYMMDD_#issueNumber_normalizedTitle.

    Args:
        issue_title: issue title
        issue_number: issue number
        date_yyyymmdd: date (YYYYMMDD). None uses today

    Returns:
        branch name within 100 chars (form: YYYYMMDD_#123_title)
    """
    if date_yyyymmdd is None:
        date_yyyymmdd = date.today().strftime("%Y%m%d")

    # An emoji/symbol-only title normalizes to empty, so fall back to a number-based slug (same as issue_helper)
    slug = normalize_title(issue_title) or f"issue-{issue_number}"
    base = f"{date_yyyymmdd}_#{issue_number}_{slug}"

    # After the 100-char cut, trim a trailing `_` left by cutting at a separator
    return base[:_MAX_BRANCH_LEN].rstrip("_")


def get_commit_template(issue_title: str, issue_url: str,
                       commit_type: str | None = None) -> str:
    """Return the commit message template. (preset fixed to projectops — skills use commit_style.render)

    Strips emoji and tags from the title and derives the commit type from that tag.
    Pasting the title as is with type fixed to feat would leave the agent to block rule-breaking commits
    and wrong version bumps by hand every time.

    Args:
        issue_title: issue title (emoji and tags allowed)
        issue_url: issue URL
        commit_type: to set it directly. Derived from the title tag when omitted

    Returns:
        commit message template string
    """
    clean_title = strip_issue_decorations(issue_title)
    resolved_type = commit_type or infer_commit_type(issue_title)
    return f"{clean_title} : {resolved_type} : {{설명}} {issue_url}"
