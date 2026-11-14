"""Repo team language: read version.yml options.language (#977)
Same pattern as the workflow source `.github/scripts/i18n/messages.py` (cannot import; test_release_language checks they match)
"""
from __future__ import annotations

import re
from pathlib import Path

# Same pattern as i18n.messages._LANG_KEY
LANGUAGE_KEY_PATTERN = re.compile(r"^\s+language:\s*[\"']?([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*)[\"']?", re.M)


def read_team_language(repo_root) -> str | None:
    """The language value in version.yml as is (ko · en · ko-KR). None if the file or key is missing"""
    version_yml = Path(repo_root) / "version.yml"
    try:
        text = version_yml.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    matched = LANGUAGE_KEY_PATTERN.search(text)
    return matched.group(1) if matched else None
