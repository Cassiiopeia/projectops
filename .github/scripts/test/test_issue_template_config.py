"""이슈 템플릿 config.yml 의 키는 GitHub 이 아는 이름이어야 한다 (#812).

오타 키(iblank_issues_enabled)는 오류 없이 무시되어 빈 이슈 막기가 조용히 꺼져 있었다.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
KNOWN = {"blank_issues_enabled", "contact_links"}


def test_issue_template_config_keys_are_known():
    for p in (ROOT / ".github").rglob("ISSUE_TEMPLATE/config.yml"):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        assert set(data) <= KNOWN, f"{p}: 알 수 없는 키 {set(data) - KNOWN}"
        assert data.get("blank_issues_enabled") is False, f"{p}: 빈 이슈 막기 설정 필요"
