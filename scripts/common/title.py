"""Extract the title from a worktree folder name and normalize it into a file-name-safe form."""

import re
from pathlib import Path
from typing import Optional


_WORKTREE_PATTERN = re.compile(r"\d{8}_\d+_(.+)$")
_ALLOWED = re.compile(r"[^\w가-힣]", re.UNICODE)
_MULTI_UNDERSCORE = re.compile(r"_+")
MAX_LENGTH = 50


def extract_from_path(cwd: str) -> Optional[str]:
    """Extract the title part of a worktree pattern from a path."""
    for part in reversed(Path(cwd).parts):
        m = _WORKTREE_PATTERN.search(part)
        if m:
            return m.group(1)
    return None


def normalize(text: str) -> str:
    """
    Normalize a title string into a file-name-safe form.

    - Spaces and hyphens → _ (pro-launch > pro_launch, so words do not merge into prolaunch)
    - Remove disallowed characters (anything other than Hangul/Latin/digits/_ is deleted)
    - Collapse consecutive underscores into one
    - At most 50 characters
    """
    # Convert spaces and hyphens to underscores
    text = text.replace(" ", "_").replace("-", "_")
    # Remove disallowed characters (only Hangul/Latin/digits/_ allowed)
    text = _ALLOWED.sub("", text)
    # Collapse consecutive underscores into one
    text = _MULTI_UNDERSCORE.sub("_", text)
    # Strip underscores at both ends
    text = text.strip("_")
    # Cut to max length, then strip trailing underscores
    return text[:MAX_LENGTH].strip("_")
