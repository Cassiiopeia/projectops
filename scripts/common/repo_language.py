"""레포 팀 언어: version.yml options.language 읽기 (#977)
워크플로우 정본 `.github/scripts/i18n/messages.py` 와 같은 패턴 (import 불가 — 일치는 test_release_language)
"""
from __future__ import annotations

import re
from pathlib import Path

# i18n.messages._LANG_KEY 와 같은 패턴
LANGUAGE_KEY_PATTERN = re.compile(r"^\s+language:\s*[\"']?([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*)[\"']?", re.M)


def read_team_language(repo_root) -> str | None:
    """version.yml 의 language 값 그대로 (ko · en · ko-KR). 파일이나 키가 없으면 None"""
    version_yml = Path(repo_root) / "version.yml"
    try:
        text = version_yml.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    matched = LANGUAGE_KEY_PATTERN.search(text)
    return matched.group(1) if matched else None
