"""CHANGELOG.md 머리말의 언어 전환(#787): 한국어는 이관 전과 같고, 영문은 영문 머리말을 쓴다."""
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import changelog_manager as cm  # noqa: E402
from i18n.messages import t  # noqa: E402


def test_머리말_문구는_카탈로그에서_온다():
    assert t("changelog.current_version", "ko") == "현재 버전"
    assert t("changelog.last_updated", "ko") == "마지막 업데이트"
    assert t("changelog.current_version", "en") == "Current version"
    assert t("changelog.last_updated", "en") == "Last updated"


def test_changelog_manager_가_머리말을_카탈로그로_쓴다():
    src = (SCRIPTS / "changelog_manager.py").read_text(encoding="utf-8")
    assert 'changelog.current_version' in src and 'changelog.last_updated' in src
    assert not re.search(r'f\.write\(f"\*\*현재 버전', src), "한글 머리말이 코드에 남아 있다"
