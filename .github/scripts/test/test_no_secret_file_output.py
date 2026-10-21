"""비밀 값이 담긴 파일을 로그에 출력하지 않는다 (#785).

실사고: Play Store · Firebase 배포가 key.properties 를 만든 직후 `cat` 으로 내용을 찍었다.
GitHub 마스킹은 값이 조금만 변형돼도 빗나가므로, 서명 비밀번호가 로그에 남을 수 있다.
모든 워크플로우(.yaml · .yml)에서 비밀 파일을 화면에 출력하는 명령을 막는다.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"

# 시크릿에서 만들어지는 파일 (서명 정보 · 키 · Firebase 설정 · .env)
_SECRET_FILE = r"(key\.properties|google-services\.json|GoogleService-Info\.plist|\.jks|\.keystore|\.p8|\.p12|\.mobileprovision|(^|[/\s\"'])\.env)"
# 파일을 화면에 내보내는 명령. 리다이렉트로 쓰는 경우(cat > f)는 제외
_PRINT = re.compile(r"^\s*(cat|head|tail|less|more|base64)\s+(?![<>])([^|>]*)$")


def workflows():
    return sorted(WF.rglob("*.y*ml"))


def _printed_secret_files(text: str):
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        match = _PRINT.match(line)
        if match and re.search(_SECRET_FILE, match.group(2)):
            hits.append(f"{number}: {line.strip()}")
    return hits


@pytest.mark.parametrize("path", workflows(), ids=lambda p: p.name)
def test_workflow_does_not_print_secret_files(path):
    hits = _printed_secret_files(path.read_text(encoding="utf-8"))
    assert not hits, f"{path.relative_to(WF)} 가 비밀 파일 내용을 출력한다: {hits}"


def test_detector_catches_known_leak_and_ignores_writes():
    # 실사고 패턴은 잡고, 파일로 쓰는 명령·무관한 파일은 통과
    assert _printed_secret_files("          cat android/key.properties")
    assert _printed_secret_files("  cat .env")
    assert not _printed_secret_files("  cat > android/key.properties << EOF")
    assert not _printed_secret_files("  cat final_release_notes.txt")
    assert not _printed_secret_files("  cat android/fastlane/Fastfile")
